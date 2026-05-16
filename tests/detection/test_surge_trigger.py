"""Tests for the surge trigger

急増トリガーテスト
``slope / mean(flow) * 100 > surge_rate_threshold_percent_per_min``
   - slope: ``HistoryDigest.window_series[edge].samples`` と
     ``Observations.arc_scalar_flows[edge]`` をマージした系列の最小二乗回帰傾き [flow/分]
   - mean(flow): 同マージ系列の流量平均

設計書 §3.4 / §3.5 / §4.3 に基づき，急増判定は履歴ウィンドウの系列に加えて
直近観測値 ``ArcScalarFlow`` も同じ系列にマージして評価する
fixture ``make_linear_series`` / ``make_flat_series`` は window + observation を
合わせて 1 本の線形系列となるよう組を返す
"""

from datetime import datetime

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
    observations: Observations,
    server_time: datetime,
    config: ResolvedConfig,
):
    return detect_normal_triggers(
        graph=graph,
        observations=observations,
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
    make_linear_series,
):
    # 全体で 0 → 100 を 10 分かけて線形増加 (履歴 10 件 + 直近観測値 1 件)
    # slope=10/min, mean=50
    # → rate = 20 %/min > 10
    window, observations = make_linear_series(
        edge_id,
        end_time=base_time,
        sample_count=11,
        start_value=0.0,
        slope_per_min=10.0,
    )
    history = HistoryDigest(window_series=(window,))

    result = _run(
        graph=basic_graph,
        history=history,
        observations=observations,
        server_time=base_time,
        config=surge_config,
    )

    assert result.triggered_edges == (edge_id,)


def test_surge_does_not_fire_when_flow_is_steady(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    surge_config: ResolvedConfig,
    make_flat_series,
):
    # 全サンプル 100 で平坦 (履歴 10 件 + 直近観測値 1 件)
    # slope=0
    # → rate=0 %/min
    window, observations = make_flat_series(
        edge_id,
        end_time=base_time,
        sample_count=11,
        value=100.0,
    )
    history = HistoryDigest(window_series=(window,))

    result = _run(
        graph=basic_graph,
        history=history,
        observations=observations,
        server_time=base_time,
        config=surge_config,
    )

    assert result.triggered_edges == ()


def test_surge_does_not_fire_when_slope_below_threshold(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    surge_config: ResolvedConfig,
    make_linear_series,
):
    # 全体で 100 → 105 を 10 分で増加 (履歴 10 件 + 直近観測値 1 件)
    # slope=0.5/min, mean=102.5
    # → rate ≈ 0.49 %/min < 10
    window, observations = make_linear_series(
        edge_id,
        end_time=base_time,
        sample_count=11,
        start_value=100.0,
        slope_per_min=0.5,
    )
    history = HistoryDigest(window_series=(window,))

    result = _run(
        graph=basic_graph,
        history=history,
        observations=observations,
        server_time=base_time,
        config=surge_config,
    )

    assert result.triggered_edges == ()


def test_surge_does_not_fire_with_insufficient_samples(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    surge_config: ResolvedConfig,
    make_scalar_observation,
):
    # 履歴ウィンドウは空，直近観測値のみ 1 件
    # 直近観測値を加えてもサンプル数 1 のみで傾きを算出できない
    # → トリガーなし
    window = ArcWindowSeries(edge_id=edge_id, samples=())
    history = HistoryDigest(window_series=(window,))
    observations = make_scalar_observation(
        edge_id, observed_at=base_time, observed_count=100.0
    )

    result = _run(
        graph=basic_graph,
        history=history,
        observations=observations,
        server_time=base_time,
        config=surge_config,
    )

    assert result.triggered_edges == ()


def test_surge_does_not_fire_when_mean_flow_is_near_zero(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    surge_config: ResolvedConfig,
    make_flat_series,
):
    # 全サンプル 0 で平均流量がほぼ 0 (履歴 10 件 + 直近観測値 1 件)
    # -> トリガーなし
    window, observations = make_flat_series(
        edge_id,
        end_time=base_time,
        sample_count=11,
        value=0.0,
    )
    history = HistoryDigest(window_series=(window,))

    result = _run(
        graph=basic_graph,
        history=history,
        observations=observations,
        server_time=base_time,
        config=surge_config,
    )

    assert result.triggered_edges == ()


def test_surge_does_not_fire_when_edge_has_no_window_data(
    base_time: datetime,
    basic_graph: Graph,
    surge_config: ResolvedConfig,
):
    # 履歴ウィンドウも直近観測値も存在しない
    # -> トリガーなし
    history = HistoryDigest()
    observations = Observations(observed_at=base_time)

    result = _run(
        graph=basic_graph,
        history=history,
        observations=observations,
        server_time=base_time,
        config=surge_config,
    )

    assert result.triggered_edges == ()


def test_surge_preserves_previous_state_queue(
    base_time: datetime,
    basic_graph: Graph,
    edge_id: EdgeID,
    surge_config: ResolvedConfig,
    make_flat_series,
):
    # トリガーなしの場合，previous_stateを維持
    # 履歴と直近観測値の両方を投入してもトリガー発火条件を満たさない
    window, observations = make_flat_series(
        edge_id,
        end_time=base_time,
        sample_count=11,
        value=100.0,
    )
    history = HistoryDigest(window_series=(window,))
    previous = DetectionState()

    result = detect_normal_triggers(
        graph=basic_graph,
        observations=observations,
        history_digest=history,
        previous_state=previous,
        server_time=base_time,
        config=surge_config,
    )

    assert result.new_state.trigger_queue == previous.trigger_queue
