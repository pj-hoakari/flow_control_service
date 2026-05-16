"""linopy + HiGHS solver wrapper for MILP Phase 1 / Phase 2 (math companion §11.4)."""

from __future__ import annotations

import time
from dataclasses import dataclass

import linopy

from ..models import PhaseStatus, ResolvedConfig
from .model_builder import BuiltModel


@dataclass(frozen=True)
class SolveOutcome:
    status: PhaseStatus
    elapsed_ms: int
    objective_value: float | None


_TERMINATION_TO_PHASE = {
    "optimal": PhaseStatus.OPTIMAL,
    "infeasible": PhaseStatus.INFEASIBLE,
    "time_limit": PhaseStatus.TIMEOUT,
}


def _map_status(model: linopy.Model) -> PhaseStatus:
    term = (model.termination_condition or "").lower()
    if term in _TERMINATION_TO_PHASE:
        return _TERMINATION_TO_PHASE[term]
    # ok でも optimal/feasible いずれかが取れない場合は ERROR
    if model.status == "ok":
        return PhaseStatus.FEASIBLE
    return PhaseStatus.ERROR


def _solver_options(seed: int, time_limit_sec: float) -> dict:
    # HiGHS の決定性確保: 並列を無効化し、random_seed を明示
    return {
        "time_limit": float(time_limit_sec),
        "random_seed": int(seed),
        "parallel": "off",
        "output_flag": False,
        "presolve": "on",
    }


def solve_phase1(built: BuiltModel, config: ResolvedConfig, seed: int) -> SolveOutcome:
    options = _solver_options(seed, config.milp_time_limit_sec)
    t0 = time.perf_counter()
    built.model.solve(solver_name="highs", io_api="direct", **options)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    status = _map_status(built.model)
    if status in (PhaseStatus.OPTIMAL, PhaseStatus.FEASIBLE):
        raw = built.model.objective.value
        obj = float(raw) if raw is not None else None
    else:
        obj = None
    return SolveOutcome(status=status, elapsed_ms=elapsed_ms, objective_value=obj)


def solve_phase2(
    built: BuiltModel,
    config: ResolvedConfig,
    seed: int,
    remaining_budget_sec: float,
) -> SolveOutcome:
    options = _solver_options(seed, max(1.0, remaining_budget_sec))
    t0 = time.perf_counter()
    built.model.solve(solver_name="highs", io_api="direct", **options)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    status = _map_status(built.model)
    if status in (PhaseStatus.OPTIMAL, PhaseStatus.FEASIBLE):
        raw = built.model.objective.value
        obj = float(raw) if raw is not None else None
    else:
        obj = None
    return SolveOutcome(status=status, elapsed_ms=elapsed_ms, objective_value=obj)
