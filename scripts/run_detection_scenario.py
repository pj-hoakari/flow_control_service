"""Run a Detection module scenario with synthetic inputs.

Usage:
    uv run python scripts/run_detection_scenario.py --scenario surge
    uv run python scripts/run_detection_scenario.py --scenario high_stagnation
    uv run python scripts/run_detection_scenario.py --scenario danger
    uv run python scripts/run_detection_scenario.py --scenario cold_start
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pprint import pprint

from flow_control.detection import DetectionResult, detect
from flow_control.models import (
    ArcHistoryStat,
    ArcStagnation,
    ArcWatchState,
    ArcWindowSeries,
    CurrentDirection,
    DetectionState,
    DirectionConstraint,
    Edge,
    Event,
    EventKind,
    Graph,
    HistoryDigest,
    Node,
    NodeKind,
    Observations,
    ObservationType,
    Reference,
    ResolvedConfig,
    TenantCategory,
    TenantContext,
)


SERVER_TIME = datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc)


def base_config() -> ResolvedConfig:
    return ResolvedConfig(
        surge_rate_threshold_percent_per_min=10.0,
        high_stagnation_duration_min=5.0,
        beta=5.0,
        cooldown_duration_min=60.0,
        warmup_duration_min=60.0,
        retrigger_warning_threshold=3,
        retrigger_reset_quiet_cycles=3,
        queue_score_threshold=10.0,
        queue_diversity_threshold=2,
    )


def base_graph() -> Graph:
    return Graph(
        nodes=(
            Node(node_id="n1", kind=NodeKind.GOAL, is_boundary=True, enabled=True),
            Node(node_id="n2", kind=NodeKind.GOAL, is_boundary=False, enabled=True),
            Node(node_id="n3", kind=NodeKind.GOAL, is_boundary=False, enabled=True),
        ),
        edges=(
            Edge(
                edge_id="e1",
                endpoint_a="n1",
                endpoint_b="n2",
                direction_constraint=DirectionConstraint.BIDIRECTIONAL_PRIOR,
                current_direction=CurrentDirection.BIDIRECTIONAL,
                enabled=True,
                observation_type=ObservationType.VECTOR,
            ),
            Edge(
                edge_id="e2",
                endpoint_a="n2",
                endpoint_b="n3",
                direction_constraint=DirectionConstraint.BIDIRECTIONAL_PRIOR,
                current_direction=CurrentDirection.BIDIRECTIONAL,
                enabled=True,
                observation_type=ObservationType.VECTOR,
            ),
        ),
    )


def long_term_tenant() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-A",
        tenant_category=TenantCategory.LONG_TERM,
        available_history_hours=240.0,
    )


def short_term_tenant() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-S",
        tenant_category=TenantCategory.SHORT_TERM,
        available_history_hours=2.0,
    )


def scenario_cold_start() -> DetectionResult:
    return detect(
        graph=base_graph(),
        observations=Observations(observed_at=SERVER_TIME),
        history_digest=HistoryDigest(completeness=0.0),
        previous_state=DetectionState(),
        events=(),
        references=Reference(),
        tenant_context=long_term_tenant(),
        config=base_config(),
        server_time=SERVER_TIME,
    )


def scenario_surge() -> DetectionResult:
    samples: list[tuple[datetime, float]] = []
    for i in range(11):
        samples.append((SERVER_TIME - timedelta(minutes=10 - i), float(i * 10)))
    window = ArcWindowSeries(edge_id="e1", samples=tuple(samples))
    hist = HistoryDigest(window_series=(window,))
    return detect(
        graph=base_graph(),
        observations=Observations(observed_at=SERVER_TIME),
        history_digest=hist,
        previous_state=DetectionState(),
        events=(),
        references=Reference(),
        tenant_context=long_term_tenant(),
        config=base_config(),
        server_time=SERVER_TIME,
    )


def scenario_high_stagnation() -> DetectionResult:
    cfg = base_config()
    started_at = SERVER_TIME - timedelta(minutes=cfg.high_stagnation_duration_min + 1)
    prev_state = replace(
        DetectionState(),
        arc_watch_states={
            "e1": ArcWatchState("e1", True, True, started_at),
        },
    )
    obs = Observations(
        observed_at=SERVER_TIME,
        arc_stagnations=(ArcStagnation("e1", 50.0),),
    )
    hist = HistoryDigest(
        arc_stats=(ArcHistoryStat("e1", p90_stagnation=20.0, baseline_stagnation=10.0),),
    )
    return detect(
        graph=base_graph(),
        observations=obs,
        history_digest=hist,
        previous_state=prev_state,
        events=(),
        references=Reference(),
        tenant_context=long_term_tenant(),
        config=cfg,
        server_time=SERVER_TIME,
    )


def scenario_danger() -> DetectionResult:
    return detect(
        graph=base_graph(),
        observations=Observations(observed_at=SERVER_TIME),
        history_digest=HistoryDigest(),
        previous_state=DetectionState(),
        events=(Event(kind=EventKind.DANGER_FLAG_UP, target_id="e2", occurred_at=SERVER_TIME),),
        references=Reference(),
        tenant_context=long_term_tenant(),
        config=base_config(),
        server_time=SERVER_TIME,
    )


def scenario_short_tenant_b2_only() -> DetectionResult:
    cfg = base_config()
    started_at = SERVER_TIME - timedelta(minutes=cfg.high_stagnation_duration_min + 1)
    prev_state = replace(
        DetectionState(),
        arc_watch_states={
            "e1": ArcWatchState("e1", True, True, started_at),
        },
    )
    return detect(
        graph=base_graph(),
        observations=Observations(
            observed_at=SERVER_TIME,
            arc_stagnations=(ArcStagnation("e1", 30.0),),
        ),
        history_digest=HistoryDigest(
            arc_stats=(ArcHistoryStat("e1", p90_stagnation=100.0, baseline_stagnation=10.0),),
        ),
        previous_state=prev_state,
        events=(),
        references=Reference(),
        tenant_context=short_term_tenant(),
        config=cfg,
        server_time=SERVER_TIME,
    )


SCENARIOS = {
    "cold_start": scenario_cold_start,
    "surge": scenario_surge,
    "high_stagnation": scenario_high_stagnation,
    "danger": scenario_danger,
    "short_tenant_b2": scenario_short_tenant_b2_only,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS.keys()),
        required=True,
        help="Detection scenario name",
    )
    args = parser.parse_args()
    result = SCENARIOS[args.scenario]()

    print(f"=== scenario: {args.scenario} ===")
    print(f"verdict_hint        : {result.verdict_hint.value}")
    print(f"triggered_edges     : {result.triggered_edges}")
    print(f"mode_flags          : {result.mode_flags}")
    print(f"evidences (count={len(result.evidences)}):")
    for ev in result.evidences:
        pprint(ev)
    print("new_state:")
    pprint(result.new_state)


if __name__ == "__main__":
    main()
