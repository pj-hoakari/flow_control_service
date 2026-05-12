"""High stagnation trigger (math companion v1 §9.2)."""

from __future__ import annotations

from datetime import timedelta

from flow_control.detection import detect
from flow_control.models import ArcHistoryStat, ArcStagnation, TriggerSource, VerdictHint

from tests.conftest import make_history, make_observations


def _stag(edge_id: str, value: float) -> ArcStagnation:
    return ArcStagnation(edge_id=edge_id, stagnation=value)


def _stat(edge_id: str, *, p90: float | None, baseline: float | None) -> ArcHistoryStat:
    return ArcHistoryStat(edge_id=edge_id, p90_stagnation=p90, baseline_stagnation=baseline)


def test_only_b1_does_not_fire(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    # b.1 のみ成立: stag(20) >= p90(10), but stag - baseline (= 19) < beta(5)?
    # stag(20) - baseline(19) = 1 < 5 (beta) → b.2 不成立
    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(_stag("e1", 20.0),),
    )
    hist = make_history(stats=(_stat("e1", p90=10.0, baseline=19.0),))

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=empty_state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.NO_TRIGGER
    watch = result.new_state.arc_watch_states["e1"]
    assert watch.percentile_satisfied is True
    assert watch.delta_satisfied is False
    assert watch.started_at is None


def test_only_b2_does_not_fire(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    # b.2 のみ成立: stag(20) - baseline(10) = 10 >= 5, p90 = 100 → b.1 不成立
    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(_stag("e1", 20.0),),
    )
    hist = make_history(stats=(_stat("e1", p90=100.0, baseline=10.0),))

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=empty_state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.NO_TRIGGER
    watch = result.new_state.arc_watch_states["e1"]
    assert watch.percentile_satisfied is False
    assert watch.delta_satisfied is True
    assert watch.started_at is None


def test_both_within_M_does_not_fire(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(_stag("e1", 50.0),),
    )
    hist = make_history(stats=(_stat("e1", p90=20.0, baseline=10.0),))

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=empty_state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.verdict_hint is VerdictHint.NO_TRIGGER
    watch = result.new_state.arc_watch_states["e1"]
    assert watch.percentile_satisfied is True
    assert watch.delta_satisfied is True
    assert watch.started_at == base_time


def test_both_continued_for_M_minutes_fires(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    # 1回目: 両方成立 → started_at = base_time, 警戒のみ
    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(_stag("e1", 50.0),),
    )
    hist = make_history(stats=(_stat("e1", p90=20.0, baseline=10.0),))

    first = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=empty_state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert first.verdict_hint is VerdictHint.NO_TRIGGER

    # 2回目: 5 分後（M 分継続済み）
    later = base_time + timedelta(minutes=baseline_config.high_stagnation_duration_min)
    obs2 = make_observations(
        observed_at=later,
        arc_stagnations=(_stag("e1", 50.0),),
    )
    second = detect(
        graph=basic_graph,
        observations=obs2,
        history_digest=hist,
        previous_state=first.new_state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=later,
    )
    assert second.verdict_hint is VerdictHint.TRIGGERED
    assert second.triggered_edges == ("e1",)
    assert any(ev.source is TriggerSource.HIGH_STAGNATION for ev in second.evidences)


def test_short_tenant_uses_b2_only(
    base_time, basic_graph, baseline_config, short_term_tenant, empty_reference, empty_state
):
    # p90 = 100 (非常に高い) なので、本来 b.1 不成立だが短期テナント縮退で b.2 のみ評価
    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(_stag("e1", 30.0),),
    )
    hist = make_history(stats=(_stat("e1", p90=100.0, baseline=10.0),))

    first = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=empty_state,
        events=(),
        references=empty_reference,
        tenant_context=short_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    # 縮退モードで b.1 = True 扱い, b.2 = (30 - 10) >= 5 → started_at = base_time
    assert first.mode_flags.degraded_short_tenant is True
    assert first.verdict_hint is VerdictHint.NO_TRIGGER

    later = base_time + timedelta(minutes=baseline_config.high_stagnation_duration_min)
    second = detect(
        graph=basic_graph,
        observations=make_observations(
            observed_at=later,
            arc_stagnations=(_stag("e1", 30.0),),
        ),
        history_digest=hist,
        previous_state=first.new_state,
        events=(),
        references=empty_reference,
        tenant_context=short_term_tenant,
        config=baseline_config,
        server_time=later,
    )
    assert second.verdict_hint is VerdictHint.TRIGGERED


def test_missing_p90_acts_as_degraded(
    base_time, basic_graph, baseline_config, long_term_tenant, empty_reference, empty_state
):
    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(_stag("e1", 30.0),),
    )
    hist = make_history(stats=(_stat("e1", p90=None, baseline=10.0),))

    result = detect(
        graph=basic_graph,
        observations=obs,
        history_digest=hist,
        previous_state=empty_state,
        events=(),
        references=empty_reference,
        tenant_context=long_term_tenant,
        config=baseline_config,
        server_time=base_time,
    )
    assert result.mode_flags.missing_percentile is True
    watch = result.new_state.arc_watch_states["e1"]
    assert watch.started_at == base_time
