"""Tests for the surge trigger

急増トリガーテスト
``slope / mean(flow) * 100 > surge_rate_threshold_percent_per_min``
   - slope: ``HistoryDigest.window_series[edge].samples`` の最小二乗回帰傾き [flow/分]
   - mean(flow): 同サンプル列の流量平均
"""

from datetime import datetime, timedelta

from flow_control.detection.config import ResolvedConfig
from flow_control.detection.history import ArcWindowSeries, HistoryDigest
from flow_control.detection.observations import Observations
from flow_control.detection.state import DetectionState
from flow_control.detection.triggers import detect_normal_triggers
from flow_control.domain import EdgeID, Graph


def _run(
    *,
    graph: Graph,
    history: HistoryDigest,
    server_time: datetime,
    config: ResolvedConfig,
):
    return detect_normal_triggers(
        graph=graph,
        observations=Observations(observed_at=server_time),
        history_digest=history,
        previous_state=DetectionState(),
        server_time=server_time,
        config=config,
    )


def test_surge_fires_when_slope_exceeds_threshold(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    surge_config: ResolvedConfig,
    make_linear_window,
):
    # 0 → 100 を 10 分で線形増加
    # slope=10/min, mean=50
    # → rate = 20 %/min > 10
    window = make_linear_window(
        edge_id,
        end_time=base_time,
        sample_count=11,
        start_value=0.0,
        slope_per_min=10.0,
    )
    history = HistoryDigest(window_series=(window,))

    result = _run(
        graph=basic_graph, history=history, server_time=base_time, config=surge_config
    )

    assert result.triggered_edges == (edge_id,)


def test_surge_does_not_fire_when_flow_is_steady(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    surge_config: ResolvedConfig,
    make_flat_window,
):
    # 全サンプル 100 で平坦
    # slope=0
    # → rate=0 %/min
    window = make_flat_window(edge_id, end_time=base_time, sample_count=11, value=100.0)
    history = HistoryDigest(window_series=(window,))

    result = _run(
        graph=basic_graph, history=history, server_time=base_time, config=surge_config
    )

    assert result.triggered_edges == ()


def test_surge_does_not_fire_when_slope_below_threshold(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    surge_config: ResolvedConfig,
    make_linear_window,
):
    # 100 → 105 を 10 分で増加
    # slope=0.5/min, mean=102.5
    # → rate ≈ 0.49 %/min < 10
    window = make_linear_window(
        edge_id,
        end_time=base_time,
        sample_count=11,
        start_value=100.0,
        slope_per_min=0.5,
    )
    history = HistoryDigest(window_series=(window,))

    result = _run(
        graph=basic_graph, history=history, server_time=base_time, config=surge_config
    )

    assert result.triggered_edges == ()


def test_surge_does_not_fire_with_insufficient_samples(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    surge_config: ResolvedConfig,
):
    # 単一サンプル
    # 傾きを算出できない
    # → トリガーなし
    window = ArcWindowSeries(
        edge_id=edge_id,
        samples=((base_time - timedelta(minutes=1), 100.0),),
    )
    history = HistoryDigest(window_series=(window,))

    result = _run(
        graph=basic_graph, history=history, server_time=base_time, config=surge_config
    )

    assert result.triggered_edges == ()


def test_surge_does_not_fire_when_mean_flow_is_near_zero(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    surge_config: ResolvedConfig,
    make_flat_window,
):
    # 平均流量がほぼ 0
    # -> トリガーなし
    window = make_flat_window(edge_id, end_time=base_time, sample_count=11, value=0.0)
    history = HistoryDigest(window_series=(window,))

    result = _run(
        graph=basic_graph, history=history, server_time=base_time, config=surge_config
    )

    assert result.triggered_edges == ()


def test_surge_does_not_fire_when_edge_has_no_window_data(
    base_time: datetime,
    basic_graph: Graph,
    surge_config: ResolvedConfig,
):
    # window_series が無い
    # -> トリガーなし
    history = HistoryDigest()

    result = _run(
        graph=basic_graph, history=history, server_time=base_time, config=surge_config
    )

    assert result.triggered_edges == ()


def test_surge_preserves_previous_state_queue(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    surge_config: ResolvedConfig,
    make_flat_window,
):
    # トリガーなしの場合，previous_stateを維持
    window = make_flat_window(edge_id, end_time=base_time, sample_count=11, value=100.0)
    history = HistoryDigest(window_series=(window,))
    previous = DetectionState()

    result = detect_normal_triggers(
        graph=basic_graph,
        observations=Observations(observed_at=base_time),
        history_digest=history,
        previous_state=previous,
        server_time=base_time,
        config=surge_config,
    )

    assert result.new_state.trigger_queue == previous.trigger_queue
