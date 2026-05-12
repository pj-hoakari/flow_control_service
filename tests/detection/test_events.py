"""Event application (module design v1 §4.3 step 2 / §4.6)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from flow_control.detection import detect
from flow_control.models import (
    Event,
    EventKind,
    RetriggerEntry,
    VerdictHint,
    make_edge_key,
    make_node_key,
)

from tests.conftest import make_history, make_observations


def test_danger_flag_up_fires_immediately(
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
    assert result.verdict_hint is VerdictHint.TRIGGERED
    assert result.triggered_edges == ("e1",)
    assert result.new_state.cooldown_until == base_time + timedelta(
        minutes=baseline_config.cooldown_duration_min
    )


def test_danger_flag_down_clears_retrigger_entry(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    state = replace(
        empty_state,
        arc_retrigger_counts={
            "e1": RetriggerEntry(count=2, quiet_cycles=0, last_fired_at=base_time)
        },
    )
    result = detect(
        graph=basic_graph,
        observations=make_observations(observed_at=base_time),
        history_digest=make_history(),
        previous_state=state,
        events=(Event(kind=EventKind.DANGER_FLAG_DOWN, target_id="e1", occurred_at=base_time),),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert "e1" not in result.new_state.arc_retrigger_counts
    assert result.verdict_hint is VerdictHint.NO_TRIGGER


def test_add_edge_extends_warmup(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    result = detect(
        graph=basic_graph,
        observations=make_observations(observed_at=base_time),
        history_digest=make_history(),
        previous_state=empty_state,
        events=(Event(kind=EventKind.ADD_EDGE, target_id="e1", occurred_at=base_time),),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert make_edge_key("e1") in result.new_state.warmup_until_by_target


def test_enable_node_event_extends_warmup(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    result = detect(
        graph=basic_graph,
        observations=make_observations(observed_at=base_time),
        history_digest=make_history(),
        previous_state=empty_state,
        events=(Event(kind=EventKind.ENABLE, target_id="n2", occurred_at=base_time),),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert make_node_key("n2") in result.new_state.warmup_until_by_target


def test_scheduled_inflow_resets_cooldown(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    state = replace(
        empty_state,
        cooldown_until=base_time + timedelta(minutes=10),
    )
    result = detect(
        graph=basic_graph,
        observations=make_observations(observed_at=base_time),
        history_digest=make_history(),
        previous_state=state,
        events=(
            Event(
                kind=EventKind.SCHEDULED_INFLOW,
                target_id="n1",
                occurred_at=base_time,
            ),
        ),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.new_state.cooldown_until is None
