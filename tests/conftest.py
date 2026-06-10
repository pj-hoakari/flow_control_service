"""Shared fixtures and factory helpers for detection tests."""

from datetime import datetime, timedelta, timezone

import pytest

from flow_control.detection.config import ResolvedConfig
from flow_control.domain.history import ArcHistoryStat, ArcWindowSeries, HistoryDigest
from flow_control.domain.observations import ArcScalarFlow, ArcStagnation, Observations
from flow_control.domain import (
    CurrentDirection,
    DirectionConstraint,
    Edge,
    EdgeID,
    Graph,
    Node,
    NodeID,
    NodeKind,
    ObservationType,
)


@pytest.fixture
def base_time() -> datetime:
    return datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def edge_id() -> EdgeID:
    return EdgeID("e1")


@pytest.fixture
def basic_graph(edge_id: EdgeID) -> Graph:
    """1 本のベクトル型エッジを持つ最小グラフ

    ``time_resolution_s`` は既定値 60 秒
    急増検出窓は ``30 + 60/60 = 31`` 分。
    """
    n1, n2 = NodeID("n1"), NodeID("n2")
    return Graph(
        nodes=(
            Node(node_id=n1, kind=NodeKind.GOAL, is_boundary=True, enabled=True),
            Node(node_id=n2, kind=NodeKind.GOAL, is_boundary=False, enabled=True),
        ),
        edges=(
            Edge(
                edge_id=edge_id,
                endpoint_a=n1,
                endpoint_b=n2,
                direction_constraint=DirectionConstraint.BIDIRECTIONAL_PRIOR,
                current_direction=CurrentDirection.BIDIRECTIONAL,
                enabled=True,
                observation_type=ObservationType.VECTOR,
            ),
        ),
    )


@pytest.fixture
def y_graph_edge_ids() -> tuple[EdgeID, EdgeID, EdgeID]:
    """Y 型グラフの 3 本のエッジ ID

    定義順は ``Graph.edges`` のタプル順 = ``enabled_edges()`` のイテレーション順と一致する
    """
    return EdgeID("e1"), EdgeID("e2"), EdgeID("e3")


@pytest.fixture
def y_graph(y_graph_edge_ids: tuple[EdgeID, EdgeID, EdgeID]) -> Graph:
    """Y 型グラフ: 中心ノード ``nc`` から 3 本のエッジが末端ノード ``n1``/``n2``/``n3`` に伸びる

    - ノード: 4 (``nc`` 中心 + ``n1``/``n2``/``n3`` 末端、末端は入退出点)
    - エッジ: 3 (``e1``: nc-n1, ``e2``: nc-n2, ``e3``: nc-n3)
    - ``time_resolution_s`` は既定値 60 秒で急増検出窓は 31 分
    """
    e1, e2, e3 = y_graph_edge_ids
    nc = NodeID("nc")
    n1, n2, n3 = NodeID("n1"), NodeID("n2"), NodeID("n3")

    def _branch(edge_id: EdgeID, leaf: NodeID) -> Edge:
        return Edge(
            edge_id=edge_id,
            endpoint_a=nc,
            endpoint_b=leaf,
            direction_constraint=DirectionConstraint.BIDIRECTIONAL_PRIOR,
            current_direction=CurrentDirection.BIDIRECTIONAL,
            enabled=True,
            observation_type=ObservationType.VECTOR,
        )

    return Graph(
        nodes=(
            Node(node_id=nc, kind=NodeKind.GOAL, is_boundary=False, enabled=True),
            Node(node_id=n1, kind=NodeKind.GOAL, is_boundary=True, enabled=True),
            Node(node_id=n2, kind=NodeKind.GOAL, is_boundary=True, enabled=True),
            Node(node_id=n3, kind=NodeKind.GOAL, is_boundary=True, enabled=True),
        ),
        edges=(_branch(e1, n1), _branch(e2, n2), _branch(e3, n3)),
    )


@pytest.fixture
def surge_config() -> ResolvedConfig:
    """急増判定の閾値: 10 %/分."""
    return ResolvedConfig(surge_rate_threshold_percent_per_min=10.0)


@pytest.fixture
def high_stagnation_config() -> ResolvedConfig:
    """高停滞判定の閾値: M=5 分, beta=1.0

    急増判定の閾値は十分に高く設定し、高停滞テストでは急増側が発火しないようにする
    """
    return ResolvedConfig(
        surge_rate_threshold_percent_per_min=1_000.0,
        high_stagnation_duration_min=5.0,
        beta=1.0,
    )


@pytest.fixture
def make_linear_series():
    """``ArcWindowSeries`` と ``ArcScalarFlow`` を合わせて 1 本の線形系列となる組を生成する

    ``sample_count`` 件のサンプルを ``observed_at`` を最終点として
    ``step_minutes`` 間隔で配置する
    系列の最終 1 件を ``ArcScalarFlow``、残り ``sample_count - 1`` 件を
    ``ArcWindowSeries.flow_samples`` として返す

    複数エッジ向けには本 fixture をエッジごとに呼び出し、返値を集約して
    ``HistoryDigest.window_series`` および ``Observations.arc_scalar_flows`` に組み立てる
    """

    def _make(
        edge_id: EdgeID,
        *,
        observed_at: datetime,
        sample_count: int,
        start_value: float,
        slope_per_min: float,
        step_minutes: float = 1.0,
    ) -> tuple[ArcWindowSeries, ArcScalarFlow]:
        span = (sample_count - 1) * step_minutes
        start_time = observed_at - timedelta(minutes=span)

        history_samples: list[tuple[datetime, float]] = []
        for i in range(sample_count - 1):
            t = start_time + timedelta(minutes=i * step_minutes)
            v = start_value + slope_per_min * (i * step_minutes)
            history_samples.append((t, v))
        window = ArcWindowSeries(edge_id=edge_id, flow_samples=tuple(history_samples))

        last_value = start_value + slope_per_min * span
        scalar_flow = ArcScalarFlow(edge_id=edge_id, observed_count=last_value)

        return window, scalar_flow

    return _make


@pytest.fixture
def make_flat_series(make_linear_series):
    """全サンプル同値で構成される線形系列の組 (``slope=0``) を生成する"""

    def _make(
        edge_id: EdgeID,
        *,
        observed_at: datetime,
        sample_count: int,
        value: float,
        step_minutes: float = 1.0,
    ) -> tuple[ArcWindowSeries, ArcScalarFlow]:
        return make_linear_series(
            edge_id,
            observed_at=observed_at,
            sample_count=sample_count,
            start_value=value,
            slope_per_min=0.0,
            step_minutes=step_minutes,
        )

    return _make


@pytest.fixture
def make_scalar_observation():
    """``observed_at`` 時点の単一 ``ArcScalarFlow`` を持つ ``Observations`` を生成する"""

    def _make(
        edge_id: EdgeID,
        *,
        observed_at: datetime,
        observed_count: float,
    ) -> Observations:
        return Observations(
            observed_at=observed_at,
            arc_scalar_flows=(
                ArcScalarFlow(edge_id=edge_id, observed_count=observed_count),
            ),
        )

    return _make


@pytest.fixture
def make_stagnation_observation():
    """``observed_at`` 時点の単一 ``ArcStagnation`` を持つ ``Observations`` を生成する"""

    def _make(
        edge_id: EdgeID,
        *,
        observed_at: datetime,
        stagnation: float,
    ) -> Observations:
        return Observations(
            observed_at=observed_at,
            arc_stagnations=(
                ArcStagnation(edge_id=edge_id, stagnation=stagnation),
            ),
        )

    return _make


@pytest.fixture
def make_history_with_arc_stats():
    """``ArcHistoryStat`` と高停滞 (b).2 用の ``stagnation_samples`` を束ねた
    ``HistoryDigest`` を組み立てる

    各エントリは ``(edge_id, p90_stagnation, recent_stagnation_ma)`` のタプルで指定する
    第 3 要素は高停滞 (b).2 の直近移動平均（数理§9.2）として ``stagnation_samples`` に
    展開される。平均は時刻に依存しないため単一サンプルで表現する
    ``p90_stagnation`` / ``recent_stagnation_ma`` は ``None`` 可
    （``None`` の場合は該当系列を生成せず (b).2 は評価不能）
    """

    # stagnation_samples の平均は時刻に依存しないため固定タイムスタンプを使う
    _ts = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def _make(
        *stats: tuple[EdgeID, float | None, float | None],
    ) -> HistoryDigest:
        return HistoryDigest(
            arc_stats=tuple(
                ArcHistoryStat(
                    edge_id=eid,
                    p90_stagnation=p90,
                    baseline_stagnation=recent_ma,
                )
                for (eid, p90, recent_ma) in stats
            ),
            window_series=tuple(
                ArcWindowSeries(edge_id=eid, stagnation_samples=((_ts, recent_ma),))
                for (eid, _p90, recent_ma) in stats
                if recent_ma is not None
            ),
        )

    return _make
