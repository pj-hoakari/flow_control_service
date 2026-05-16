"""Frozen dataclass / immutability tests for new models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from flow_control.models import (
    Commodity,
    DetourResult,
    DetourSet,
    DirectionProposal,
    FallbackReport,
    ForecastResult,
    ImportanceDirection,
    ObjectiveValues,
    OptimizationResult,
    Path,
    ProposedDirection,
    RouteImportance,
    SolverStatus,
    freeze_float_map,
)


def test_commodity_frozen():
    c = Commodity("a", "b", 1.0)
    with pytest.raises(FrozenInstanceError):
        c.demand = 2.0  # type: ignore[misc]


def test_forecast_result_defaults():
    fr = ForecastResult()
    assert fr.commodities == ()
    assert dict(fr.arc_flow_sensitivity) == {}
    assert dict(fr.arc_baseline_stagnation) == {}
    assert isinstance(fr.fallback_usage, FallbackReport)


def test_forecast_result_uses_immutable_mapping():
    fr = ForecastResult(arc_flow_sensitivity=freeze_float_map({"e1": 1.0}))
    with pytest.raises(TypeError):
        fr.arc_flow_sensitivity["e1"] = 2.0  # type: ignore[index]


def test_detour_result_all_path_edge_ids_union():
    dr = DetourResult(
        detour_sets=(
            DetourSet(
                origin_edge_id="e1",
                endpoint_pair=("n1", "n2"),
                paths=(Path(edge_ids=("e2", "e3")),),
                k_effective=1,
            ),
            DetourSet(
                origin_edge_id="e4",
                endpoint_pair=("n2", "n3"),
                paths=(Path(edge_ids=("e5",)),),
                k_effective=1,
            ),
        ),
    )
    assert dr.all_path_edge_ids() == frozenset({"e1", "e2", "e3", "e4", "e5"})


def test_detour_result_empty():
    dr = DetourResult()
    assert dr.detour_sets == ()
    assert dr.all_path_edge_ids() == frozenset()


def test_optimization_result_hashable():
    r = OptimizationResult(
        route_importance=(
            RouteImportance(edge_id="e1", direction=ImportanceDirection.A_TO_B, importance=1.0),
        ),
        direction_proposal=(
            DirectionProposal(edge_id="e1", proposed_direction=ProposedDirection.A_TO_B),
        ),
        objective_values=ObjectiveValues(tau_star=0.5, throughput=2.0),
        solver_status=SolverStatus.OPTIMAL,
        solved_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
        seed=0,
    )
    # frozen dataclass は hashable
    hash(r)


def test_proposed_direction_enum_values():
    assert ProposedDirection.A_TO_B.value == "A_TO_B"
    assert ProposedDirection.B_TO_A.value == "B_TO_A"
    assert ProposedDirection.BIDIRECTIONAL.value == "BIDIRECTIONAL"
    assert ProposedDirection.BLOCKED.value == "BLOCKED"


def test_solver_status_values():
    expected = {"OPTIMAL", "FEASIBLE", "INFEASIBLE", "TIMEOUT", "SKIPPED", "ERROR"}
    actual = {s.value for s in SolverStatus}
    assert actual == expected
