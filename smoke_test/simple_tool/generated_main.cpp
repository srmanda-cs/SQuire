#include "clang/StaticAnalyzer/Core/Checker.h"
#include "clang/StaticAnalyzer/Core/BugReporter/BugType.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/CheckerContext.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/CallEvent.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/ProgramStateTrait.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/SVals.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/SymbolManager.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/ProgramState.h"
#include "clang/StaticAnalyzer/Frontend/CheckerRegistry.h"
#include <optional>
#include <memory>

using namespace clang;
using namespace ento;

namespace {

enum {
  Nullness_MaybeNull = 0,
  Nullness_CheckedNonNull = 1
};

REGISTER_MAP_WITH_PROGRAMSTATE(RegionNullness, const MemRegion *, int)

class NPDChecker : public Checker<
                       check::PostCall,
                       check::BranchCondition,
                       check::Bind,
                       check::Location,
                       check::DeadSymbols> {
  mutable std::unique_ptr<BugType> BT;

public:
  NPDChecker()
      : BT(std::make_unique<BugType>(
            this, "Unchecked NULL pointer dereference", "Nullability")) {}

  void check::PostCall(const CallEvent &Call, CheckerContext &C) const;
  void checkBranchCondition(const Stmt *Condition, CheckerContext &C) const;
  void checkBind(SVal L, SVal V, const Stmt *S, CheckerContext &C) const;
  void checkLocation(SVal L, bool IsLoad, const Stmt *S,
                     CheckerContext &C) const;
  void check::DeadSymbols(SymbolReaper &SR, CheckerContext &C) const;

private:
  bool isInterestingAllocator(const FunctionDecl *FD) const;
  bool isIDTableMetadataExpr(const Expr *E) const;
  const MemRegion *getBaseRegionFromLocation(SVal L) const;
  bool isDefinitelyNonNull(SVal V, ProgramStateRef State,
                           CheckerContext &C) const;
  void reportUnchecked(const Expr *DerefExpr, CheckerContext &C,
                       const MemRegion *R) const;
};

bool NPDChecker::isInterestingAllocator(const FunctionDecl *FD) const {
  if (!FD)
    return false;
  QualType RT = FD->getReturnType();
  if (!RT->isPointerType())
    return false;
  IdentifierInfo *II = FD->getIdentifier();
  if (!II)
    return false;
  StringRef Name = II->getName();
  if (Name == "malloc" || Name == "calloc" || Name == "realloc" ||
      Name == "strdup")
    return true;
  if (Name.starts_with("kmalloc") || Name == "kzalloc" ||
      Name.starts_with("kcalloc") || Name.starts_with("kvmalloc") ||
      Name.starts_with("vmalloc") || Name == "vzalloc" ||
      Name.starts_with("devm_kmalloc") || Name.starts_with("ioremap") ||
      Name.starts_with("devm_ioremap"))
    return true;
  return false;
}

bool NPDChecker::isIDTableMetadataExpr(const Expr *E) const {
  E = E->IgnoreParenCasts();
  const auto *ME = dyn_cast<MemberExpr>(E);
  if (!ME)
    return false;
  const FieldDecl *FD = dyn_cast<FieldDecl>(ME->getMemberDecl());
  if (!FD)
    return false;
  IdentifierInfo *II = FD->getIdentifier();
  if (!II)
    return false;
  StringRef Name = II->getName();
  if (Name == "driver_data" || Name == "driver_info")
    return true;
  return false;
}

const MemRegion *NPDChecker::getBaseRegionFromLocation(SVal L) const {
  std::optional<loc::MemRegionVal> M = L.getAs<loc::MemRegionVal>();
  if (!M)
    return nullptr;
  const MemRegion *R = M->getRegion();
  if (!R)
    return nullptr;
  const MemRegion *Base = R;
  while (true) {
    if (const auto *ER = dyn_cast<ElementRegion>(Base))
      Base = ER->getSuperRegion();
    else if (const auto *FR = dyn_cast<FieldRegion>(Base))
      Base = FR->getSuperRegion();
    else
      break;
  }
  return Base;
}

bool NPDChecker::isDefinitelyNonNull(SVal V, ProgramStateRef State,
                                     CheckerContext &C) const {
  auto &CM = C.getConstraintManager();
  ConditionTruthVal IsNull = CM.isNull(State, V);
  if (IsNull.isConstrainedTrue())
    return false;
  ConditionTruthVal IsNonNull = CM.isNonNull(State, V);
  return IsNonNull.isConstrainedTrue();
}

void NPDChecker::check::PostCall(const CallEvent &Call,
                               CheckerContext &C) const {
  const FunctionDecl *FD = dyn_cast_or_null<FunctionDecl>(Call.getDecl());
  if (!isInterestingAllocator(FD))
    return;

  SVal Ret = Call.getReturnValue();
  const MemRegion *R = Ret.getAsRegion();
  if (!R)
    return;

  ProgramStateRef State = C.getState();
  State = State->set<RegionNullness>(R, Nullness_MaybeNull);
  C.addTransition(State);
}

void NPDChecker::checkBranchCondition(const Stmt *Condition,
                                      CheckerContext &C) const {
  const Expr *E = dyn_cast_or_null<Expr>(Condition);
  if (!E)
    return;
  E = E->IgnoreParenCasts();
  const MemRegion *R = nullptr;
  bool NonNull = false;

  if (const auto *UO = dyn_cast<UnaryOperator>(E)) {
    if (UO->getOpcode() == UO_LNot) {
      const Expr *Sub = UO->getSubExpr()->IgnoreParenCasts();
      SVal V = C.getSVal(Sub);
      if (auto LR = V.getAs<loc::MemRegionVal>()) {
        R = LR->getRegion();
        NonNull = false;
      }
    }
  } else if (const auto *BO = dyn_cast<BinaryOperator>(E)) {
    if (BO->isComparisonOp()) {
      const Expr *LHS = BO->getLHS()->IgnoreParenCasts();
      const Expr *RHS = BO->getRHS()->IgnoreParenCasts();
      const Expr *PtrExpr = nullptr;
      const Expr *NullExpr = nullptr;
      if (LHS->getType()->isPointerType() && RHS->isNullPointerConstant(
                                                C.getASTContext(),
                                                Expr::NPC_ValueDependentIsNull)) {
        PtrExpr = LHS;
        NullExpr = RHS;
      } else if (RHS->getType()->isPointerType() &&
                 LHS->isNullPointerConstant(C.getASTContext(),
                                            Expr::NPC_ValueDependentIsNull)) {
        PtrExpr = RHS;
        NullExpr = LHS;
      }
      (void)NullExpr;
      if (PtrExpr) {
        SVal V = C.getSVal(PtrExpr);
        if (auto LR = V.getAs<loc::MemRegionVal>()) {
          R = LR->getRegion();
          BinaryOperatorKind Op = BO->getOpcode();
          if (Op == BO_EQ || Op == BO_LE || Op == BO_LT)
            NonNull = false;
          else
            NonNull = true;
        }
      }
    }
  } else {
    SVal V = C.getSVal(E);
    if (auto LR = V.getAs<loc::MemRegionVal>()) {
      R = LR->getRegion();
      NonNull = true;
    }
  }

  if (!R)
    return;

  ProgramStateRef State = C.getState();
  auto It = State->get<RegionNullness>().lookup(R);
  if (!It || *It != Nullness_MaybeNull)
    return;

  if (NonNull) {
    State = State->set<RegionNullness>(R, Nullness_CheckedNonNull);
    C.addTransition(State);
  }
}

void NPDChecker::checkBind(SVal L, SVal V, const Stmt *S,
                           CheckerContext &C) const {
  const MemRegion *LR = L.getAsRegion();
  if (!LR)
    return;

  ProgramStateRef State = C.getState();
  auto Map = State->get<RegionNullness>();

  const MemRegion *RR = V.getAsRegion();
  if (RR) {
    auto It = Map.lookup(RR);
    if (It) {
      State = State->set<RegionNullness>(LR, *It);
      C.addTransition(State);
      return;
    }
  }

  if (const auto *E = dyn_cast_or_null<Expr>(S)) {
    const Expr *RHS = nullptr;
    if (const auto *BO = dyn_cast<BinaryOperator>(E))
      RHS = BO->getRHS();
    else if (const auto *DS = dyn_cast<DeclStmt>(E)) {
      if (const auto *VD = dyn_cast<VarDecl>(DS->getSingleDecl()))
        RHS = VD->getInit();
    }
    if (RHS && isIDTableMetadataExpr(RHS)) {
      State = State->set<RegionNullness>(LR, Nullness_MaybeNull);
      C.addTransition(State);
    }
  }
}

void NPDChecker::reportUnchecked(const Expr *DerefExpr, CheckerContext &C,
                                 const MemRegion *R) const {
  if (!DerefExpr)
    return;
  ExplodedNode *N = C.generateErrorNode();
  if (!N)
    return;
  auto Rpt = std::make_unique<PathSensitiveBugReport>(
      *BT, "Result of a possibly failing allocation or metadata access is "
           "used without a preceding NULL check",
      N);
  Rpt->addRange(DerefExpr->getSourceRange());
  C.emitReport(std::move(Rpt));
}

void NPDChecker::checkLocation(SVal L, bool IsLoad, const Stmt *S,
                               CheckerContext &C) const {
  (void)IsLoad;
  const MemRegion *Base = getBaseRegionFromLocation(L);
  if (!Base)
    return;

  ProgramStateRef State = C.getState();
  auto It = State->get<RegionNullness>().lookup(Base);
  if (!It || *It != Nullness_MaybeNull)
    return;

  SVal PtrV = State->getSVal(Base);
  if (isDefinitelyNonNull(PtrV, State, C))
    return;

  const Expr *E = dyn_cast_or_null<Expr>(S);
  reportUnchecked(E ? E : nullptr, C, Base);
}

void NPDChecker::check::DeadSymbols(SymbolReaper &SR, CheckerContext &C) const {
  ProgramStateRef State = C.getState();
  auto Map = State->get<RegionNullness>();
  for (auto I : Map) {
    const MemRegion *R = I.first;
    if (!SR.isLiveRegion(R))
      Map = Map.remove(R);
  }
  State = State->set<RegionNullness>(Map);
  C.addTransition(State);
}

} // namespace

extern "C" void clang_registerCheckers(CheckerRegistry &registry) {
  registry.addChecker<NPDChecker>(
      "squire.NPDChecker", "Detect unchecked NULL pointer dereferences", "");
}
