#include "clang/StaticAnalyzer/Core/Checker.h"
#include "clang/StaticAnalyzer/Core/BugReporter/BugType.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/CheckerContext.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/CallEvent.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/ProgramStateTrait.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/SVals.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/SymbolManager.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/ProgramState.h"
#include "clang/StaticAnalyzer/Frontend/CheckerRegistry.h"

#include <memory>

using namespace clang;
using namespace ento;

enum {
  Nullness_MaybeNull = 0,
  Nullness_CheckedNonNull = 1
};

REGISTER_MAP_WITH_PROGRAMSTATE(RegionNullness, const MemRegion *, int)

namespace {

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

  void checkPostCall(const CallEvent &Call, CheckerContext &C) const;
  void checkBranchCondition(const Stmt *Condition, CheckerContext &C) const;
  void checkBind(SVal L, SVal V, const Stmt *S, CheckerContext &C) const;
  void checkLocation(SVal L, bool IsLoad, const Stmt *S,
                     CheckerContext &C) const;
  void checkDeadSymbols(SymbolReaper &SR, CheckerContext &C) const;

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
  if (!E)
    return false;

  E = E->IgnoreParenCasts();
  const auto *ME = dyn_cast<MemberExpr>(E);
  if (!ME)
    return false;

  const auto *FD = dyn_cast<FieldDecl>(ME->getMemberDecl());
  if (!FD)
    return false;

  IdentifierInfo *II = FD->getIdentifier();
  if (!II)
    return false;

  StringRef Name = II->getName();

  return (Name == "driver_data" || Name == "driver_info");
}

const MemRegion *NPDChecker::getBaseRegionFromLocation(SVal L) const {
  if (std::optional<loc::MemRegionVal> M = L.getAs<loc::MemRegionVal>()) {
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
  return nullptr;
}

bool NPDChecker::isDefinitelyNonNull(SVal V, ProgramStateRef State,
                                     CheckerContext &) const {
  if (!V.getAs<Loc>())
    return false;

  DefinedOrUnknownSVal Cond = V.castAs<DefinedOrUnknownSVal>();
  auto Assumption = State->assume(Cond);
  ProgramStateRef StateNonZero = Assumption.first;
  ProgramStateRef StateZero    = Assumption.second;

  return (StateNonZero && !StateZero);
}


void NPDChecker::checkPostCall(const CallEvent &Call,
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
  }

  else if (const auto *BO = dyn_cast<BinaryOperator>(E)) {
    if (BO->isComparisonOp()) {
      const Expr *LHS = BO->getLHS()->IgnoreParenCasts();
      const Expr *RHS = BO->getRHS()->IgnoreParenCasts();
      const Expr *PtrExpr = nullptr;

      if (LHS->getType()->isPointerType() &&
          RHS->isNullPointerConstant(C.getASTContext(),
                                     Expr::NPC_ValueDependentIsNull)) {
        PtrExpr = LHS;
      } else if (RHS->getType()->isPointerType() &&
                 LHS->isNullPointerConstant(C.getASTContext(),
                                            Expr::NPC_ValueDependentIsNull)) {
        PtrExpr = RHS;
      }

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
  }
  else {
    SVal V = C.getSVal(E);
    if (auto LR = V.getAs<loc::MemRegionVal>()) {
      R = LR->getRegion();
      NonNull = true;
    }
  }

  if (!R)
    return;

  ProgramStateRef State = C.getState();
  RegionNullnessTy Map = State->get<RegionNullness>();
  if (const int *Val = Map.lookup(R)) {
    if (*Val == Nullness_MaybeNull && NonNull) {
      State = State->set<RegionNullness>(R, Nullness_CheckedNonNull);
      C.addTransition(State);
    }
  }
}

void NPDChecker::checkBind(SVal L, SVal V, const Stmt *S,
                           CheckerContext &C) const {
  const MemRegion *LR = L.getAsRegion();
  if (!LR)
    return;

  ProgramStateRef State = C.getState();
  RegionNullnessTy Map = State->get<RegionNullness>();

  if (const MemRegion *RR = V.getAsRegion()) {
    if (const int *Val = Map.lookup(RR)) {
      State = State->set<RegionNullness>(LR, *Val);
      C.addTransition(State);
      return;
    }
  }

  if (const auto *E = dyn_cast_or_null<Expr>(S)) {
    const Expr *RHS = nullptr;

    if (const auto *BO = dyn_cast<BinaryOperator>(E)) {
      if (BO->getOpcode() == BO_Assign)
        RHS = BO->getRHS();
    } else if (const auto *DS = dyn_cast<DeclStmt>(E)) {
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
  (void)R;

  if (!DerefExpr)
    return;

  ExplodedNode *N = C.generateErrorNode();
  if (!N)
    return;

  auto Rpt = std::make_unique<PathSensitiveBugReport>(
      *BT,
      "Result of a possibly failing allocation or metadata access is "
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
  RegionNullnessTy Map = State->get<RegionNullness>();
  const int *Val = Map.lookup(Base);
  if (!Val || *Val != Nullness_MaybeNull)
    return;

  if (isDefinitelyNonNull(L, State, C))
    return;

  const Expr *E = dyn_cast_or_null<Expr>(S);
  reportUnchecked(E ? E : nullptr, C, Base);
}

void NPDChecker::checkDeadSymbols(SymbolReaper &SR, CheckerContext &C) const {
  ProgramStateRef State = C.getState();
  RegionNullnessTy Map = State->get<RegionNullness>();

  for (const auto &Entry : Map) {
    const MemRegion *R = Entry.first;
    if (!SR.isLiveRegion(R)) {
      State = State->remove<RegionNullness>(R);
    }
  }

  C.addTransition(State);
}

}

extern "C" void clang_registerCheckers(CheckerRegistry &registry) {
  registry.addChecker<NPDChecker>(
      "squire.NPDChecker", "Detect unchecked NULL pointer dereferences", "");
}

extern "C" const char clang_analyzerAPIVersionString[] =
    CLANG_ANALYZER_API_VERSION_STRING;
