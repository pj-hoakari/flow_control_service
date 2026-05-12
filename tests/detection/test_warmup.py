"""Warmup behaviour (module design v1 §4.4)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from types import MappingProxyType

from flow_control.detection import detect
from flow_control.models import (
    DetectionState,
    Event,
    EventKind,
    VerdictHint,
    make_edge_key,
    make_node_key,
)

from tests.conftest import make_history, make_observations


def _all_enabled_keys(graph):
    keys: list[str] = []
    for n in graph.nodes:
        if n.enabled:
            keys.append(make_node_key(n.node_id))
    for e in graph.edges:
        if e.enabled:
            keys.append(make_edge_key(e.edge_id))
    return keys


def test_skipped_warmup_when_all_targets_within_window(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    until = base_time + timedelta(minutes=baseline_config.warmup_duration_min)
    warmup_map = MappingProxyType({key: until for key in _all_enabled_keys(basic_graph)})
    state = replace(empty_state, warmup_until_by_target=warmup_map)

    obs = make_observations(observed_at=base_time)
    hist = make_history()

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.SKIPPED_WARMUP
    assert result.triggered_edges == ()


def test_danger_flag_overrides_warmup(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    until = base_time + timedelta(minutes=baseline_config.warmup_duration_min)
    warmup_map = MappingProxyType({key: until for key in _all_enabled_keys(basic_graph)})
    state = replace(empty_state, warmup_until_by_target=warmup_map)

    event = Event(
        kind=EventKind.DANGER_FLAG_UP,
        target_id="e1",
        occurred_at=base_time,
    )
    obs = make_observations(observed_at=base_time)
    hist = make_history()

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=state,
        events=(event,),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.TRIGGERED
    assert "e1" in result.triggered_edges


def test_partial_warmup_does_not_block(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    # 1 つの edge だけ warmup 中、もう片方は通常判定が走るので NO_TRIGGER
    until = base_time + timedelta(minutes=baseline_config.warmup_duration_min)
    warmup_map = MappingProxyType({make_edge_key("e1"): until})
    state = replace(empty_state, warmup_until_by_target=warmup_map)

    obs = make_observations(observed_at=base_time)
    hist = make_history()

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.NO_TRIGGER


def test_warmup_expired_passes_through(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    until = base_time - timedelta(minutes=1)
    warmup_map = MappingProxyType({key: until for key in _all_enabled_keys(basic_graph)})
    state = replace(empty_state, warmup_until_by_target=warmup_map)

    obs = make_observations(observed_at=base_time)
    hist = make_history()

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.NO_TRIGGER


def test_event_extends_warmup_for_added_node(
    base_time,
    basic_graph,
    baseline_config,
    long_term_tenant,
    empty_reference,
    empty_state,
):
    event = Event(
        kind=EventKind.ADD_NODE,
        target_id="n_new",
        occurred_at=base_time,
    )
    result = detect(
        graph=basic_graph,
        observations=make_observations(observed_at=base_time),
        history_digest=make_history(),
        previous_state=empty_state,
        events=(event,),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    key = make_node_key("n_new")
    assert key in result.new_state.warmup_until_by_target
    assert result.new_state.warmup_until_by_target[key] == base_time + timedelta(
        minutes=baseline_config.warmup_duration_min
    )
