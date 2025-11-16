#include "clang/StaticAnalyzer/Core/Checker.h"
#include "clang/StaticAnalyzer/Core/BugReporter/BugType.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/CheckerContext.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/CallEvent.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/ProgramStateTrait.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/SVals.h"
#include "clang/StaticAnalyzer/Frontend/CheckerRegistry.h"
#include <memory>
#include <optional>

using namespace clang;
using namespace ento;

// Must be at global scope; macro already inserts the correct namespace
REGISTER_MAP_WITH_PROGRAMSTATE(RegionNullness, const MemRegion *, int)

namespace
{

  enum NullFlags
  {
    NS_MaybeNull = 1 << 0,
    NS_CheckedNonNull = 1 << 1,
    NS_Reported = 1 << 2
  };

  class NPDChecker final
      : public Checker<check::PostCall, check::BranchCondition, check::Bind,
                       check::Location, check::PreStmt<MemberExpr>,
                       check::PreStmt<ArraySubscriptExpr>, check::DeadSymbols>
  {
    mutable std::unique_ptr<BugType> BT;

  public:
    NPDChecker()
        : BT(std::make_unique<BugType>(
              this, "Unchecked NULL pointer dereference", "Nullability")) {}

    void checkPostCall(const CallEvent &, CheckerContext &) const;
    void checkBranchCondition(const Stmt *, CheckerContext &) const;
    void checkBind(SVal Loc, SVal Val, const Stmt *, CheckerContext &) const;
    void checkLocation(SVal Loc, bool isLoad, const Stmt *, CheckerContext &) const;
    void checkPreStmt(const MemberExpr *, CheckerContext &) const;
    void checkPreStmt(const ArraySubscriptExpr *, CheckerContext &) const;
    void checkDeadSymbols(SymbolReaper &, CheckerContext &) const;

  private:
    static bool isMaybeNullSource(llvm::StringRef Name)
    {
      return Name == "kmalloc" || Name == "kzalloc" || Name == "kvmalloc";
    }

    void reportIfNull(const Expr *Base, const Stmt *UseSite,
                      CheckerContext &C) const
    {
      const MemRegion *R = C.getSVal(Base).getAsRegion();
      if (!R)
        return;
      auto St = C.getState();
      if (auto F = St->get<RegionNullness>(R))
        if (*F & NS_MaybeNull)
        {
          ExplodedNode *N = C.generateNonFatalErrorNode(St);
          if (!N)
            return;
          auto Rep = std::make_unique<PathSensitiveBugReport>(
              *BT, "Possible NULL dereference", N);
          Rep->addRange(UseSite->getSourceRange());
          C.emitReport(std::move(Rep));
          C.addTransition(St->set<RegionNullness>(R, *F | NS_Reported));
        }
    }
  };

  void NPDChecker::checkPostCall(const CallEvent &Call, CheckerContext &C) const
  {
    if (const IdentifierInfo *II = Call.getCalleeIdentifier())
    {
      if (isMaybeNullSource(II->getName()))
      {
        const MemRegion *R = Call.getReturnValue().getAsRegion();
        if (!R)
          return;
        auto St = C.getState()->set<RegionNullness>(R, NS_MaybeNull);
        C.addTransition(St);
      }
    }
  }

  void NPDChecker::checkBranchCondition(const Stmt *, CheckerContext &) const
  {
    // could mark checked-non-null here
  }

  void NPDChecker::checkBind(SVal L, SVal V, const Stmt *, CheckerContext &C) const
  {
    const MemRegion *Dst = L.getAsRegion();
    if (!Dst)
      return;
    auto St = C.getState();
    if (auto Src = V.getAsRegion())
    {
      if (auto F = St->get<RegionNullness>(Src))
        C.addTransition(St->set<RegionNullness>(Dst, *F & NS_MaybeNull));
    }
  }

  void NPDChecker::checkLocation(SVal, bool, const Stmt *S,
                                 CheckerContext &C) const
  {
    if (const Expr *E = dyn_cast_or_null<Expr>(S))
      reportIfNull(E, S, C);
  }

  void NPDChecker::checkPreStmt(const MemberExpr *ME, CheckerContext &C) const
  {
    reportIfNull(ME->getBase(), ME, C);
  }

  void NPDChecker::checkPreStmt(const ArraySubscriptExpr *ASE,
                                CheckerContext &C) const
  {
    reportIfNull(ASE->getBase(), ASE, C);
  }

  void NPDChecker::checkDeadSymbols(SymbolReaper &SR, CheckerContext &C) const
  {
    auto St = C.getState();
    for (auto &Pair : St->get<RegionNullness>())
      if (!SR.isLiveRegion(Pair.first))
        St = St->remove<RegionNullness>(Pair.first);
    if (St != C.getState())
      C.addTransition(St);
  }

} // namespace

extern "C" void clang_registerCheckers(CheckerRegistry &registry)
{
  registry.addChecker<NPDChecker>(
      "squire.NPDChecker", "Detect unchecked NULL pointer dereferences", "");
}