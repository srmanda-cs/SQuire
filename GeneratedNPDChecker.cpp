#include "clang/StaticAnalyzer/Core/Checker.h"
#include "clang/StaticAnalyzer/Core/BugReporter/BugType.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/CheckerContext.h"
#include "clang/StaticAnalyzer/Frontend/CheckerRegistry.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/CallEvent.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/ProgramStateTrait.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/SVals.h"
#include "clang/AST/Expr.h"
#include <optional>
#include <memory>

using namespace clang;
using namespace ento;

namespace {

enum PointerStateKind {
  PSK_Unknown = 0,
  PSK_MaybeNull = 1,
  PSK_NonNull = 2
};

REGISTER_MAP_WITH_PROGRAMSTATE(RegionNullness, const MemRegion *, int)

class NPDChecker
    : public Checker< check::PostCall,
                      check::BranchCondition,
                      check::Bind,
                      check::Location,
                      check::DeadSymbols > {
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
  bool isModeledAlloc(const CallEvent &Call) const;
  const MemRegion *getBaseRegionOfExpr(const Expr *E, ProgramStateRef State,
                                       const LocationContext *LC) const;
  ProgramStateRef setRegionState(ProgramStateRef State, const MemRegion *MR,
                                 PointerStateKind K) const;
  PointerStateKind getRegionState(ProgramStateRef State,
                                  const MemRegion *MR) const;
  void reportBug(const Expr *DerefExpr, CheckerContext &C,
                 const MemRegion *MR) const;
};

bool NPDChecker::isModeledAlloc(const CallEvent &Call) const {
  const FunctionDecl *FD = dyn_cast_or_null<FunctionDecl>(Call.getDecl());
  if (!FD)
    return false;
  IdentifierInfo *II = FD->getIdentifier();
  if (!II)
    return false;
  llvm::StringRef Name = II->getName();
  return Name == "malloc" || Name == "calloc" || Name == "realloc" ||
         Name == "strdup" || Name == "kzalloc" || Name == "kmalloc" ||
         Name == "kvmalloc" || Name == "kvmalloc_array" ||
         Name == "vzalloc" || Name == "vmalloc" ||
         Name == "devm_kmalloc" || Name == "devm_kzalloc" ||
         Name == "ioremap";
}

const MemRegion *NPDChecker::getBaseRegionOfExpr(const Expr *E,
                                                 ProgramStateRef State,
                                                 const LocationContext *LC) const {
  if (!E)
    return nullptr;
  E = E->IgnoreParenCasts();
  if (const auto *ME = dyn_cast<MemberExpr>(E)) {
    const Expr *Base = ME->getBase()->IgnoreParenCasts();
    SVal BaseVal = State->getSVal(Base, LC);
    if (const MemRegion *MR = BaseVal.getAsRegion())
      return MR;
  }
  if (const auto *ASE = dyn_cast<ArraySubscriptExpr>(E)) {
    const Expr *Base = ASE->getBase()->IgnoreParenCasts();
    SVal BaseVal = State->getSVal(Base, LC);
    if (const MemRegion *MR = BaseVal.getAsRegion())
      return MR;
  }
  SVal V = State->getSVal(E, LC);
  if (const MemRegion *MR = V.getAsRegion())
    return MR;
  return nullptr;
}

ProgramStateRef NPDChecker::setRegionState(ProgramStateRef State,
                                           const MemRegion *MR,
                                           PointerStateKind K) const {
  if (!MR)
    return State;
  if (K == PSK_Unknown)
    return State->remove<RegionNullness>(MR);
  return State->set<RegionNullness>(MR, static_cast<int>(K));
}

PointerStateKind NPDChecker::getRegionState(ProgramStateRef State,
                                            const MemRegion *MR) const {
  if (!MR)
    return PSK_Unknown;
  const std::optional<int> V = State->get<RegionNullness>(MR);
  if (!V)
    return PSK_Unknown;
  int I = *V;
  if (I == PSK_MaybeNull)
    return PSK_MaybeNull;
  if (I == PSK_NonNull)
    return PSK_NonNull;
  return PSK_Unknown;
}

void NPDChecker::check::PostCall(const CallEvent &Call,
                               CheckerContext &C) const {
  if (!isModeledAlloc(Call))
    return;
  SVal Ret = Call.getReturnValue();
  const MemRegion *MR = Ret.getAsRegion();
  if (!MR)
    return;
  ProgramStateRef State = C.getState();
  State = setRegionState(State, MR, PSK_MaybeNull);
  C.addTransition(State);
}

void NPDChecker::checkBranchCondition(const Stmt *Condition,
                                      CheckerContext &C) const {
  const Expr *E = dyn_cast_or_null<Expr>(Condition);
  if (!E)
    return;
  E = E->IgnoreParenCasts();
  const Expr *PtrExpr = nullptr;
  bool CheckNonNullOnTrue = false;
  if (const auto *UO = dyn_cast<UnaryOperator>(E)) {
    if (UO->getOpcode() == UO_LNot) {
      PtrExpr = UO->getSubExpr()->IgnoreParenCasts();
      CheckNonNullOnTrue = false;
    }
  } else if (const auto *BO = dyn_cast<BinaryOperator>(E)) {
    if (BO->isComparisonOp()) {
      const Expr *L = BO->getLHS()->IgnoreParenCasts();
      const Expr *R = BO->getRHS()->IgnoreParenCasts();
      bool LIsNull =
          isa<IntegerLiteral>(L) || isa<CXXNullPtrLiteralExpr>(L);
      bool RIsNull =
          isa<IntegerLiteral>(R) || isa<CXXNullPtrLiteralExpr>(R);
      if (LIsNull ^ RIsNull) {
        PtrExpr = LIsNull ? R : L;
        if (BO->getOpcode() == BO_EQ)
          CheckNonNullOnTrue = false;
        else if (BO->getOpcode() == BO_NE)
          CheckNonNullOnTrue = true;
      }
    }
  } else {
    PtrExpr = E;
    CheckNonNullOnTrue = true;
  }
  if (!PtrExpr)
    return;
  ProgramStateRef State = C.getState();
  const MemRegion *MR =
      getBaseRegionOfExpr(PtrExpr, State, C.getLocationContext());
  if (!MR)
    return;
  bool TookTrue = C.isTrue();
  if ((CheckNonNullOnTrue && TookTrue) ||
      (!CheckNonNullOnTrue && !TookTrue)) {
    State = setRegionState(State, MR, PSK_NonNull);
    C.addTransition(State);
  }
}

void NPDChecker::checkBind(SVal L, SVal V, const Stmt *S,
                           CheckerContext &C) const {
  const MemRegion *LMR = L.getAsRegion();
  if (!LMR)
    return;
  ProgramStateRef State = C.getState();
  const MemRegion *RMR = V.getAsRegion();
  if (RMR) {
    PointerStateKind RK = getRegionState(State, RMR);
    if (RK != PSK_Unknown) {
      State = setRegionState(State, LMR, RK);
      C.addTransition(State);
      return;
    }
  }
  if (V.isZeroConstant()) {
    State = setRegionState(State, LMR, PSK_MaybeNull);
    C.addTransition(State);
    return;
  }
  if (V.getSubKind() == nonloc::PointerToMemberKind ||
      V.getSubKind() == nonloc::PointerToDataMemberKind) {
    State = setRegionState(State, LMR, PSK_NonNull);
    C.addTransition(State);
    return;
  }
}

void NPDChecker::reportBug(const Expr *DerefExpr, CheckerContext &C,
                           const MemRegion *MR) const {
  if (!BT)
    return;
  ExplodedNode *N = C.generateErrorNode();
  if (!N)
    return;
  auto R = std::make_unique<PathSensitiveBugReport>(
      *BT,
      "Pointer may be NULL; it is dereferenced here without a dominating NULL check",
      N);
  if (DerefExpr)
    R->addRange(DerefExpr->getSourceRange());
  C.emitReport(std::move(R));
}

void NPDChecker::checkLocation(SVal L, bool IsLoad, const Stmt *S,
                               CheckerContext &C) const {
  const Expr *E = dyn_cast_or_null<Expr>(S);
  ProgramStateRef State = C.getState();
  const LocationContext *LC = C.getLocationContext();
  const MemRegion *Base = nullptr;
  if (const auto *ME = dyn_cast_or_null<MemberExpr>(E)) {
    Base = getBaseRegionOfExpr(ME->getBase(), State, LC);
  } else if (const auto *UO = dyn_cast_or_null<UnaryOperator>(E)) {
    if (UO->getOpcode() == UO_Deref)
      Base = getBaseRegionOfExpr(UO->getSubExpr(), State, LC);
  } else if (const auto *ASE = dyn_cast_or_null<ArraySubscriptExpr>(E)) {
    Base = getBaseRegionOfExpr(ASE->getBase(), State, LC);
  }
  if (!Base)
    Base = L.getAsRegion();
  if (!Base)
    return;
  PointerStateKind K = getRegionState(State, Base);
  if (K == PSK_MaybeNull)
    reportBug(E, C, Base);
}

void NPDChecker::check::DeadSymbols(SymbolReaper &SR,
                                  CheckerContext &C) const {
  ProgramStateRef State = C.getState();
  RegionNullnessTy Map = State->get<RegionNullness>();
  for (auto It = Map.begin(), End = Map.end(); It != End; ++It) {
    const MemRegion *MR = It->first;
    if (const auto *SRM = dyn_cast<SymbolicRegion>(MR)) {
      SymbolRef Sym = SRM->getSymbol();
      if (!SR.isLive(Sym))
        State = State->remove<RegionNullness>(MR);
    }
  }
  C.addTransition(State);
}

} // namespace

extern "C" void clang_registerCheckers(CheckerRegistry &registry) {
  registry.addChecker<NPDChecker>(
      "squire.NPDChecker",
      "Detect unchecked NULL pointer dereferences", "");
}