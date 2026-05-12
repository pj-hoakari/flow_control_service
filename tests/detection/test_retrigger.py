"""Retrigger counters (module design v1 §4.7)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from flow_control.detection import detect
from flow_control.models import (
    ArcHistoryStat,
    ArcStagnation,
    ArcWatchState,
    Event,
    EventKind,
    Graph,
    RetriggerEntry,
)

from tests.conftest import make_edge, make_history, make_node, make_observations


def _ready_to_fire_state(base_time, baseline_config, edge_id="e1", existing_count=0):
    started_at = base_time - timedelta(minutes=baseline_config.high_stagnation_duration_min + 1)
    return replace(
        __import__(
            "flow_control.models", fromlist=["DetectionState"]
        ).DetectionState(),
        arc_watch_states={
            edge_id: ArcWatchState(
                edge_id=edge_id,
                percentile_satisfied=True,
                delta_satisfied=True,
                started_at=started_at,
            )
        },
        arc_retrigger_counts={
            edge_id: RetriggerEntry(count=existing_count, quiet_cycles=0, last_fired_at=None)
        }
        if existing_count
        else {},
    )


def _high_stag_obs(base_time, edge_ids):
    return make_observations(
        observed_at=base_time,
        arc_stagnations=tuple(ArcStagnation(eid, 50.0) for eid in edge_ids),
    )


def _high_stag_hist(edge_ids):
    return make_history(
        stats=tuple(ArcHistoryStat(eid, 20.0, 10.0) for eid in edge_ids),
    )


def test_same_edge_fire_increments_count(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference
):
    state = _ready_to_fire_state(base_time, baseline_config, edge_id="e1", existing_count=2)
    result = detect(
        graph=basic_graph,
        observations=_high_stag_obs(base_time, ["e1"]),
        history_digest=_high_stag_hist(["e1"]),
        previous_state=state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.new_state.arc_retrigger_counts["e1"].count == 3


def test_different_origin_resets_existing(
    base_time, baseline_config, long_term_tenant, empty_reference
):
    graph = Graph(
        nodes=(make_node("n1"), make_node("n2"), make_node("n3")),
        edges=(make_edge("e1", "n1", "n2"), make_edge("e2", "n2", "n3")),
    )
    started_at = base_time - timedelta(minutes=baseline_config.high_stagnation_duration_min + 1)
    state = replace(
        __import__(
            "flow_control.models", fromlist=["DetectionState"]
        ).DetectionState(),
        arc_watch_states={
            "e2": ArcWatchState("e2", True, True, started_at),
        },
        arc_retrigger_counts={
            "e1": RetriggerEntry(count=5, quiet_cycles=0, last_fired_at=base_time),
        },
    )
    result = detect(
        graph=graph,
        observations=_high_stag_obs(base_time, ["e2"]),
        history_digest=_high_stag_hist(["e2"]),
        previous_state=state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.new_state.arc_retrigger_counts["e1"].count == 0
    assert result.new_state.arc_retrigger_counts["e2"].count == 1


def test_quiet_cycles_reset_after_N(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference
):
    state = replace(
        __import__(
            "flow_control.models", fromlist=["DetectionState"]
        ).DetectionState(),
        arc_retrigger_counts={
            "e1": RetriggerEntry(
                count=3,
                quiet_cycles=baseline_config.retrigger_reset_quiet_cycles - 1,
                last_fired_at=base_time - timedelta(minutes=60),
            )
        },
    )
    result = detect(
        graph=basic_graph,
        observations=make_observations(observed_at=base_time),
        history_digest=make_history(),
        previous_state=state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    entry = result.new_state.arc_retrigger_counts["e1"]
    assert entry.count == 0
    assert entry.quiet_cycles == 0


def test_disabled_edge_drops_entry(
    base_time, baseline_config, long_term_tenant, empty_reference
):
    graph = Graph(
        nodes=(make_node("n1"), make_node("n2")),
        edges=(make_edge("e1", "n1", "n2", enabled=False),),
    )
    state = replace(
        __import__(
            "flow_control.models", fromlist=["DetectionState"]
        ).DetectionState(),
        arc_retrigger_counts={
            "e1": RetriggerEntry(count=4, quiet_cycles=0, last_fired_at=base_time),
        },
    )
    result = detect(
        graph=graph,
        observations=make_observations(observed_at=base_time),
        history_digest=make_history(),
        previous_state=state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert "e1" not in result.new_state.arc_retrigger_counts


def test_danger_flag_does_not_count_in_retrigger(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    result = detect(
        graph=basic_graph,
        observations=make_observations(observed_at=base_time),
        history_digest=make_history(),
        previous_state=empty_state,
        events=(Event(kind=EventKind.DANGER_FLAG_UP, target_id="e1", occurred_at=base_time),),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    # 危険フラグ起源のみで通常発火がない場合、カウント対象外
    assert "e1" not in result.new_state.arc_retrigger_counts
