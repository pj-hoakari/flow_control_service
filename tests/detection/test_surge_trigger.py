"""Tests for the surge trigger

急増トリガーテスト
``slope / mean(flow) * 100 > surge_rate_threshold_percent_per_min``
   - slope: ``HistoryDigest.window_series[edge].samples`` と
     ``Observations.arc_scalar_flows[edge]`` をマージした系列の最小二乗回帰傾き [flow/分]
   - mean(flow): 同マージ系列の流量平均

設計書 §3.4 / §3.5 / §4.3 に基づき，急増判定は履歴ウィンドウの系列に加えて
直近観測値 ``ArcScalarFlow`` も同じ系列にマージして評価する

fixture ``make_linear_series`` / ``make_flat_series`` は window + scalar_flow が
全体で 1 本の線形系列となるよう ``(ArcWindowSeries, ArcScalarFlow)`` の組を返す
"""

from datetime import datetime

import pytest

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
    window, scalar_flow = make_linear_series(
        edge_id,
        observed_at=base_time,
        sample_count=11,
        start_value=0.0,
        slope_per_min=10.0,
    )
    history = HistoryDigest(window_series=(window,))
    observations = Observations(observed_at=base_time, arc_scalar_flows=(scalar_flow,))

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
    window, scalar_flow = make_flat_series(
        edge_id,
        observed_at=base_time,
        sample_count=11,
        value=100.0,
    )
    history = HistoryDigest(window_series=(window,))
    observations = Observations(observed_at=base_time, arc_scalar_flows=(scalar_flow,))

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
    window, scalar_flow = make_linear_series(
        edge_id,
        observed_at=base_time,
        sample_count=11,
        start_value=100.0,
        slope_per_min=0.5,
    )
    history = HistoryDigest(window_series=(window,))
    observations = Observations(observed_at=base_time, arc_scalar_flows=(scalar_flow,))

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
    window, scalar_flow = make_flat_series(
        edge_id,
        observed_at=base_time,
        sample_count=11,
        value=0.0,
    )
    history = HistoryDigest(window_series=(window,))
    observations = Observations(observed_at=base_time, arc_scalar_flows=(scalar_flow,))

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
    window, scalar_flow = make_flat_series(
        edge_id,
        observed_at=base_time,
        sample_count=11,
        value=100.0,
    )
    history = HistoryDigest(window_series=(window,))
    observations = Observations(observed_at=base_time, arc_scalar_flows=(scalar_flow,))
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


# ---------------------------------------------------------------------------
# Y 型グラフ (3 エッジ) 上での複数エッジ状態組み合わせテスト
# ---------------------------------------------------------------------------


def _surging_pair(make_linear_series, edge_id: EdgeID, observed_at: datetime):
    """急増 (slope=10/min, mean=50, rate=20 %/分) となる (window, scalar_flow) を返す"""
    return make_linear_series(
        edge_id,
        observed_at=observed_at,
        sample_count=11,
        start_value=0.0,
        slope_per_min=10.0,
    )


def _calm_pair(make_flat_series, edge_id: EdgeID, observed_at: datetime):
    """平坦 (slope=0) で発火しない (window, scalar_flow) を返す"""
    return make_flat_series(
        edge_id,
        observed_at=observed_at,
        sample_count=11,
        value=100.0,
    )


def test_y_graph_no_trigger_when_all_edges_calm(
    base_time: datetime,
    y_graph: Graph,
    y_graph_edge_ids: tuple[EdgeID, EdgeID, EdgeID],
    surge_config: ResolvedConfig,
    make_flat_series,
):
    # 3 エッジすべてが平坦
    # → トリガーなし
    pairs = [_calm_pair(make_flat_series, eid, base_time) for eid in y_graph_edge_ids]
    history = HistoryDigest(window_series=tuple(w for w, _ in pairs))
    observations = Observations(
        observed_at=base_time, arc_scalar_flows=tuple(s for _, s in pairs)
    )

    result = _run(
        graph=y_graph,
        history=history,
        observations=observations,
        server_time=base_time,
        config=surge_config,
    )

    assert result.triggered_edges == ()


@pytest.mark.parametrize("surging_index", [0, 1, 2])
def test_y_graph_fires_only_on_surging_edge(
    base_time: datetime,
    y_graph: Graph,
    y_graph_edge_ids: tuple[EdgeID, EdgeID, EdgeID],
    surge_config: ResolvedConfig,
    make_linear_series,
    make_flat_series,
    surging_index: int,
):
    # 3 エッジのうち 1 本のみ急増 (残り 2 本は平坦)
    # → 該当エッジ 1 件が triggered_edges に入る
    pairs = []
    for i, eid in enumerate(y_graph_edge_ids):
        if i == surging_index:
            pairs.append(_surging_pair(make_linear_series, eid, base_time))
        else:
            pairs.append(_calm_pair(make_flat_series, eid, base_time))
    history = HistoryDigest(window_series=tuple(w for w, _ in pairs))
    observations = Observations(
        observed_at=base_time, arc_scalar_flows=tuple(s for _, s in pairs)
    )

    result = _run(
        graph=y_graph,
        history=history,
        observations=observations,
        server_time=base_time,
        config=surge_config,
    )

    assert result.triggered_edges == (y_graph_edge_ids[surging_index],)


def test_y_graph_returns_all_surging_edges_when_multiple_qualify(
    base_time: datetime,
    y_graph: Graph,
    y_graph_edge_ids: tuple[EdgeID, EdgeID, EdgeID],
    surge_config: ResolvedConfig,
    make_linear_series,
    make_flat_series,
):
    # e1 / e3 が急増、e2 のみ平坦
    # → ``triggered_edges`` には e1, e3 の両方が含まれる
    e1, e2, e3 = y_graph_edge_ids
    w1, s1 = _surging_pair(make_linear_series, e1, base_time)
    w2, s2 = _calm_pair(make_flat_series, e2, base_time)
    w3, s3 = _surging_pair(make_linear_series, e3, base_time)
    history = HistoryDigest(window_series=(w1, w2, w3))
    observations = Observations(observed_at=base_time, arc_scalar_flows=(s1, s2, s3))

    result = _run(
        graph=y_graph,
        history=history,
        observations=observations,
        server_time=base_time,
        config=surge_config,
    )

    assert set(result.triggered_edges) == {e1, e3}
    assert len(result.triggered_edges) == 2  # 重複なし
