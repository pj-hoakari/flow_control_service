"""Tests for warmup

ウォームアップ判定テスト

- ENABLE/ADD_* イベントで対象別ウォームアップ終了予定を設定する
- ウォームアップ中の対象は通常トリガー判定を停止する（個別管理）
- 全対象がウォームアップ中かつ危険フラグなしなら SKIPPED_WARMUP
- 危険フラグはウォームアップ中でも有効
"""

from datetime import datetime, timedelta

from flow_control.detection.config import ResolvedConfig
from flow_control.detection.detector import detect
from flow_control.domain.history import HistoryDigest
from flow_control.domain.observations import Observations
from flow_control.detection.state import DetectionState, WarmupState
from flow_control.detection.triggers import (
    Event,
    EventKind,
    VerdictHint,
    all_targets_in_warmup,
    apply_warmup_events,
)
from flow_control.domain import EdgeID, Graph


def _config(
    *, warmup_min: float = 60.0, surge_threshold: float = 10.0
) -> ResolvedConfig:
    return ResolvedConfig(
        surge_rate_threshold_percent_per_min=surge_threshold,
        warmup_duration_min=warmup_min,
    )


def _surge_inputs(
    edge_id: EdgeID, base_time: datetime, make_linear_series
) -> tuple[HistoryDigest, Observations]:
    window, scalar_flow = make_linear_series(
        edge_id,
        observed_at=base_time,
        sample_count=11,
        start_value=0.0,
        slope_per_min=10.0,
    )
    history = HistoryDigest(window_series=(window,))
    observations = Observations(observed_at=base_time, arc_scalar_flows=(scalar_flow,))
    return history, observations


def _event(kind: EventKind, target_id: str, at: datetime) -> Event:
    return Event(kind=kind, target_id=target_id, occurred_at=at)


# ---------------------------------------------------------------------------
# apply_warmup_events
# ---------------------------------------------------------------------------


def test_enable_event_sets_warmup_until(base_time: datetime):
    events = (_event(EventKind.ENABLE, "edge:e1", base_time),)

    state = apply_warmup_events(
        DetectionState(), events, base_time, _config(warmup_min=60.0)
    )

    assert state.warmup_until_of("edge:e1") == base_time + timedelta(minutes=60.0)
    assert state.is_in_warmup("edge:e1", base_time) is True


def test_add_node_event_sets_warmup_until(base_time: datetime):
    events = (_event(EventKind.ADD_NODE, "node:n1", base_time),)

    state = apply_warmup_events(DetectionState(), events, base_time, _config())

    assert state.warmup_until_of("node:n1") == base_time + timedelta(minutes=60.0)


def test_non_warmup_events_do_not_set_warmup(base_time: datetime):
    events = (
        _event(EventKind.DANGER_FLAG_UP, "edge:e1", base_time),
        _event(EventKind.SCHEDULED_INFLOW, "node:n1", base_time),
        _event(EventKind.DISABLE, "edge:e2", base_time),
    )

    state = apply_warmup_events(DetectionState(), events, base_time, _config())

    assert state.warmup_states == ()


def test_apply_warmup_events_returns_same_state_when_no_change(base_time: datetime):
    previous = DetectionState()

    state = apply_warmup_events(previous, (), base_time, _config())

    assert state is previous


def test_warmup_expires_after_duration(base_time: datetime):
    state = DetectionState(
        warmup_states=(
            WarmupState(target_key="edge:e1", until=base_time + timedelta(minutes=60)),
        )
    )

    assert state.is_in_warmup("edge:e1", base_time) is True
    # 終了予定時刻ちょうどは警戒対象外（< 判定）
    assert state.is_in_warmup("edge:e1", base_time + timedelta(minutes=60)) is False


# ---------------------------------------------------------------------------
# all_targets_in_warmup
# ---------------------------------------------------------------------------


def test_all_targets_in_warmup_true_when_every_target_warming(
    base_time: datetime, basic_graph: Graph
):
    until = base_time + timedelta(minutes=60)
    state = DetectionState(
        warmup_states=(
            WarmupState(target_key="edge:e1", until=until),
            WarmupState(target_key="node:n1", until=until),
            WarmupState(target_key="node:n2", until=until),
        )
    )

    assert all_targets_in_warmup(state, basic_graph, base_time) is True


def test_all_targets_in_warmup_false_when_one_active(
    base_time: datetime, basic_graph: Graph
):
    until = base_time + timedelta(minutes=60)
    # n2 を含めないため全対象ウォームアップにはならない
    state = DetectionState(
        warmup_states=(
            WarmupState(target_key="edge:e1", until=until),
            WarmupState(target_key="node:n1", until=until),
        )
    )

    assert all_targets_in_warmup(state, basic_graph, base_time) is False


def test_all_targets_in_warmup_false_for_empty_graph(base_time: datetime):
    assert all_targets_in_warmup(DetectionState(), Graph(), base_time) is False


# ---------------------------------------------------------------------------
# detect() 結線
# ---------------------------------------------------------------------------


def test_detect_skips_when_all_targets_in_warmup(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    make_linear_series,
):
    # 急増が成立する入力でも、全対象ウォームアップ中なら判定をスキップする
    history, observations = _surge_inputs(edge_id, base_time, make_linear_series)
    until = base_time + timedelta(minutes=60)
    previous = DetectionState(
        warmup_states=(
            WarmupState(target_key="edge:e1", until=until),
            WarmupState(target_key="node:n1", until=until),
            WarmupState(target_key="node:n2", until=until),
        )
    )

    result = detect(
        graph=basic_graph,
        observations=observations,
        history_digest=history,
        previous_state=previous,
        events=(),
        config=_config(),
        server_time=base_time,
    )

    assert result.verdict_hint == VerdictHint.SKIPPED_WARMUP
    assert result.triggered_edges == ()
    assert result.new_state.cooldown_until is None


def test_detect_suppresses_normal_trigger_for_warmup_edge(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    make_linear_series,
):
    # edge:e1 のみウォームアップ中。node は警戒外なので全対象ウォームアップではない
    # → SKIPPED_WARMUP にはならず、ただし e1 の急増は抑止されるため NO_TRIGGER
    history, observations = _surge_inputs(edge_id, base_time, make_linear_series)
    previous = DetectionState(
        warmup_states=(
            WarmupState(target_key="edge:e1", until=base_time + timedelta(minutes=60)),
        )
    )

    result = detect(
        graph=basic_graph,
        observations=observations,
        history_digest=history,
        previous_state=previous,
        events=(),
        config=_config(),
        server_time=base_time,
    )

    assert result.verdict_hint == VerdictHint.NO_TRIGGER
    assert result.triggered_edges == ()


def test_danger_flag_fires_even_when_all_targets_in_warmup(
    base_time: datetime,
    basic_graph: Graph,
):
    until = base_time + timedelta(minutes=60)
    previous = DetectionState(
        warmup_states=(
            WarmupState(target_key="edge:e1", until=until),
            WarmupState(target_key="node:n1", until=until),
            WarmupState(target_key="node:n2", until=until),
        )
    )
    observations = Observations(observed_at=base_time)

    result = detect(
        graph=basic_graph,
        observations=observations,
        history_digest=HistoryDigest(),
        previous_state=previous,
        events=(_event(EventKind.DANGER_FLAG_UP, "edge:e1", base_time),),
        config=_config(),
        server_time=base_time,
    )

    assert result.verdict_hint == VerdictHint.TRIGGERED
    assert result.triggered_edges == (EdgeID("e1"),)
    assert result.new_state.cooldown_until == base_time + timedelta(minutes=60.0)


def test_newly_enabled_edge_is_warmed_up_same_request(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    make_linear_series,
):
    # 同一リクエストで ENABLE された edge:e1 は即ウォームアップ対象となり急増が抑止される。
    # node は警戒外なので全対象ウォームアップにはならず NO_TRIGGER
    history, observations = _surge_inputs(edge_id, base_time, make_linear_series)

    result = detect(
        graph=basic_graph,
        observations=observations,
        history_digest=history,
        previous_state=DetectionState(),
        events=(_event(EventKind.ENABLE, "edge:e1", base_time),),
        config=_config(),
        server_time=base_time,
    )

    assert result.verdict_hint == VerdictHint.NO_TRIGGER
    assert result.triggered_edges == ()
    # ウォームアップ状態は新しい検知状態に引き継がれる
    assert result.new_state.is_in_warmup("edge:e1", base_time) is True
