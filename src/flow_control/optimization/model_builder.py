"""MILP builder for the Optimization Step (math companion §11)."""
# pyright: reportArgumentType=false, reportIndexIssue=false
# 理由: linopy の Variable.loc[str] は型スタブが弱く、実行時には問題なく動くが
# Pyright では str を不正なキーとして検出する。本ファイル内の検査を抑制する。

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import linopy
import pandas as pd

from ..models import (
    Commodity,
    ConfidenceFlag,
    ForecastResult,
    Graph,
    Observations,
    ResolvedConfig,
)
from .arc_index import ArcIndex


@dataclass
class BuiltModel:
    """linopy モデルと求解に必要な脇情報をまとめたもの。

    `dataclass(frozen=False)` にしている理由: linopy モデルはミューテーションを伴う
    （Phase 2 で objective 差し替え）ため、純粋関数の中で構築・破棄するが内部状態として
    再代入を許容する。
    """

    model: linopy.Model
    x: linopy.Variable
    f_per_k: linopy.Variable | None  # commodity が 0 件の場合は None
    f_total: linopy.Variable
    tau: linopy.Variable
    y_out: linopy.Variable
    y_in: linopy.Variable
    big_m: float
    representative_entry: str
    arc_index: ArcIndex
    commodities: tuple[Commodity, ...]
    commodity_index: pd.Index
    eta_eff: Mapping[str, float]
    s_obs_eff: Mapping[str, float]
    s_bar_eff: Mapping[str, float]


_PHASE1_OBJECTIVE_NAME = "phase1_min_tau"
_PHASE2_TAU_BOUND_NAME = "phase2_tau_bound"


def build_phase1_model(
    graph: Graph,
    observations: Observations,
    forecast_result: ForecastResult,
    config: ResolvedConfig,
    arc_index: ArcIndex,
) -> BuiltModel:
    """Open モード 2段階 MILP のフェーズ 1 (`min τ`) を構築する。

    Open モードであることを前提とする (`arc_index.entry_nodes` が非空)。
    """
    del graph  # arc_index 経由でアクセスする

    if not arc_index.entry_nodes:
        raise ValueError("build_phase1_model: Open モード前提だが entry_nodes が空")

    m = linopy.Model()

    arc_ids = pd.Index([a.arc_id for a in arc_index.arcs], name="arc")
    commodities = forecast_result.commodities
    commodity_index = pd.Index([f"k{i}" for i in range(len(commodities))], name="commodity")

    # ── 変数定義 (math companion §11.1) ──
    x = m.add_variables(lower=0, upper=1, integer=True, coords=[arc_ids], name="x")
    if len(commodities) > 0:
        f_per_k = m.add_variables(lower=0, coords=[arc_ids, commodity_index], name="f_per_k")
    else:
        f_per_k = None
    f_total = m.add_variables(lower=0, coords=[arc_ids], name="f_total")
    tau = m.add_variables(lower=0, name="tau")
    y_out = m.add_variables(lower=0, coords=[arc_ids], name="y_out")
    y_in = m.add_variables(lower=0, coords=[arc_ids], name="y_in")

    # ── 定数 ──
    total_demand = sum(c.demand for c in commodities)
    finite_caps = [a.danger_capacity for a in arc_index.arcs if a.danger_capacity is not None]
    max_cap = max(finite_caps, default=0.0)
    big_m = config.big_m_factor * (total_demand + max_cap + 1.0)
    n_active = len(arc_index.nodes_active)
    representative = arc_index.entry_nodes[0]

    # ── 観測・パラメータマップ ──
    eta_eff = _build_eta_map(arc_index, forecast_result)
    s_obs_eff = _build_s_obs_map(arc_index, observations)
    s_bar_eff = _build_s_bar_map(arc_index, forecast_result, s_obs_eff)
    sigma_by_edge = _build_sigma_map(observations)

    # ── 制約: 方向属性 (§11.2.1) ──
    for arc in arc_index.arcs:
        if arc.alpha == 0:
            m.add_constraints(x.loc[arc.arc_id] == 0, name=f"alpha_zero_{arc.arc_id}")
        else:
            # alpha = 1 のとき x_a <= 1 は変数境界で既に成立
            if arc.beta == 1:
                m.add_constraints(x.loc[arc.arc_id] == 1, name=f"beta_one_{arc.arc_id}")

    # 各エッジで少なくとも 1 方向有効
    for edge_id, (a2b, b2a) in arc_index.by_edge.items():
        m.add_constraints(x.loc[a2b.arc_id] + x.loc[b2a.arc_id] >= 1, name=f"edge_oneway_{edge_id}")

    # ── 制約: フロー結合 (§11.2.2) ──
    if f_per_k is not None:
        for arc in arc_index.arcs:
            for k_label in commodity_index:
                m.add_constraints(
                    f_per_k.loc[arc.arc_id, k_label] - big_m * x.loc[arc.arc_id] <= 0,
                    name=f"fk_M_{arc.arc_id}_{k_label}",
                )

        # f_total = sum_k f_per_k
        for arc in arc_index.arcs:
            terms = [f_per_k.loc[arc.arc_id, k_label] for k_label in commodity_index]
            m.add_constraints(f_total.loc[arc.arc_id] - _safe_sum(terms) == 0,
                              name=f"ftotal_{arc.arc_id}")
    else:
        # commodity 0 件: f_total は 0 で固定
        for arc in arc_index.arcs:
            m.add_constraints(f_total.loc[arc.arc_id] == 0, name=f"ftotal_zero_{arc.arc_id}")

    # 容量上限 (危険フラグ)
    for arc in arc_index.arcs:
        if arc.danger_capacity is not None:
            m.add_constraints(
                f_total.loc[arc.arc_id] <= arc.danger_capacity,
                name=f"cap_{arc.arc_id}",
            )

    # スカラー型アークのパンク制約 (math companion §11.2.2 末尾)
    for arc in arc_index.arcs:
        if arc.is_scalar and arc.danger_capacity is not None:
            sigma = sigma_by_edge.get(arc.edge_id, 0.0)
            cap = max(0.0, arc.danger_capacity - sigma)
            m.add_constraints(f_total.loc[arc.arc_id] <= cap, name=f"scalar_punc_{arc.arc_id}")

    # ── 制約: フロー保存 (§11.2.3) ──
    if f_per_k is not None:
        for k_idx, commodity in enumerate(commodities):
            k_label = commodity_index[k_idx]
            for node_id in arc_index.nodes_active:
                outs = arc_index.by_node_out.get(node_id, ())
                ins = arc_index.by_node_in.get(node_id, ())
                out_terms = [f_per_k.loc[a.arc_id, k_label] for a in outs]
                in_terms = [f_per_k.loc[a.arc_id, k_label] for a in ins]
                if node_id == commodity.origin_node_id:
                    rhs = commodity.demand
                elif node_id == commodity.destination_node_id:
                    rhs = -commodity.demand
                else:
                    rhs = 0.0
                m.add_constraints(
                    _safe_sum(out_terms) - _safe_sum(in_terms) == rhs,
                    name=f"conserve_{node_id}_{k_label}",
                )

    # ── 制約: ローカル可達性 (§11.2.4) ──
    for node_id in arc_index.nodes_active:
        outs = arc_index.by_node_out.get(node_id, ())
        ins = arc_index.by_node_in.get(node_id, ())
        if outs:
            m.add_constraints(_safe_sum([x.loc[a.arc_id] for a in outs]) >= 1,
                              name=f"reach_out_{node_id}")
        if ins:
            m.add_constraints(_safe_sum([x.loc[a.arc_id] for a in ins]) >= 1,
                              name=f"reach_in_{node_id}")

    # ── 制約: 入退出点ペア間可達性 (§11.2.5, Open のみ) ──
    for node_id in arc_index.nodes_active:
        outs = arc_index.by_node_out.get(node_id, ())
        ins = arc_index.by_node_in.get(node_id, ())
        # y_out: r がソース、他がシンク
        if node_id == representative:
            b_out = float(n_active - 1)
            b_in = -float(n_active - 1)
        else:
            b_out = -1.0
            b_in = 1.0
        m.add_constraints(
            _safe_sum([y_out.loc[a.arc_id] for a in outs])
            - _safe_sum([y_out.loc[a.arc_id] for a in ins])
            == b_out,
            name=f"y_out_conserve_{node_id}",
        )
        m.add_constraints(
            _safe_sum([y_in.loc[a.arc_id] for a in outs])
            - _safe_sum([y_in.loc[a.arc_id] for a in ins])
            == b_in,
            name=f"y_in_conserve_{node_id}",
        )

    # y_* <= N * x_a
    for arc in arc_index.arcs:
        m.add_constraints(y_out.loc[arc.arc_id] - n_active * x.loc[arc.arc_id] <= 0,
                          name=f"y_out_M_{arc.arc_id}")
        m.add_constraints(y_in.loc[arc.arc_id] - n_active * x.loc[arc.arc_id] <= 0,
                          name=f"y_in_M_{arc.arc_id}")

    # ── 制約: τ 線形化 (§11.3) ──
    for arc in arc_index.arcs:
        s_bar = s_bar_eff.get(arc.edge_id, 0.0)
        s_obs = s_obs_eff.get(arc.edge_id, 0.0)
        eta = eta_eff.get(arc.edge_id, 0.0)
        # tau * (s_bar + eps_0) >= s_obs - eta * f_total
        # ⇔ tau * (s_bar + eps_0) + eta * f_total >= s_obs
        coef_tau = s_bar + config.epsilon_0
        m.add_constraints(
            coef_tau * tau + eta * f_total.loc[arc.arc_id] >= s_obs,
            name=f"tau_link_{arc.arc_id}",
        )

    # ── Phase 1 目的: min tau ──
    m.add_objective(1.0 * tau, sense="min")

    return BuiltModel(
        model=m,
        x=x,
        f_per_k=f_per_k,
        f_total=f_total,
        tau=tau,
        y_out=y_out,
        y_in=y_in,
        big_m=big_m,
        representative_entry=representative,
        arc_index=arc_index,
        commodities=commodities,
        commodity_index=commodity_index,
        eta_eff=eta_eff,
        s_obs_eff=s_obs_eff,
        s_bar_eff=s_bar_eff,
    )


def add_phase2_constraints_and_objective(
    built: BuiltModel,
    target_arc_ids: tuple[str, ...],
    tau_star: float,
    config: ResolvedConfig,
) -> None:
    """Phase 2 (`max Σ_{a∈P} f_a` subject to `τ ≤ τ* + ε`) のための制約・目的を追加。

    target_arc_ids が空ならば呼び出し側で SKIPPED を選ぶこと。
    """
    if not target_arc_ids:
        raise ValueError("add_phase2_constraints_and_objective: target_arc_ids が空")

    built.model.add_constraints(
        1.0 * built.tau <= tau_star + config.epsilon,
        name=_PHASE2_TAU_BOUND_NAME,
    )

    terms = [built.f_total.loc[arc_id] for arc_id in target_arc_ids]
    built.model.remove_objective()
    built.model.add_objective(_safe_sum(terms), sense="max")


def collect_p_arc_ids(
    arc_index: ArcIndex,
    target_edge_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """対象エッジ集合 P (config + detour 由来) を実在する有向アーク ID に展開する。"""
    seen: dict[str, None] = {}
    for edge_id in target_edge_ids:
        pair = arc_index.by_edge.get(edge_id)
        if pair is None:
            continue
        for arc in pair:
            seen[arc.arc_id] = None
    return tuple(seen.keys())


def _build_eta_map(arc_index: ArcIndex, forecast_result: ForecastResult) -> Mapping[str, float]:
    out: dict[str, float] = {}
    for arc in arc_index.arcs:
        if arc.edge_id in out:
            continue
        out[arc.edge_id] = float(forecast_result.arc_flow_sensitivity.get(arc.edge_id, 0.0))
    return out


def _build_s_obs_map(arc_index: ArcIndex, observations: Observations) -> Mapping[str, float]:
    by_edge: dict[str, float] = {}
    for stag in observations.arc_stagnations:
        if stag.confidence_flag is ConfidenceFlag.INVALID:
            by_edge[stag.edge_id] = 0.0
        else:
            by_edge[stag.edge_id] = float(stag.stagnation)
    # 観測が無いエッジは 0 として扱う (τ 制約を実質的に無効化)
    result: dict[str, float] = {}
    for arc in arc_index.arcs:
        if arc.edge_id in result:
            continue
        result[arc.edge_id] = by_edge.get(arc.edge_id, 0.0)
    return result


def _build_s_bar_map(
    arc_index: ArcIndex,
    forecast_result: ForecastResult,
    s_obs_eff: Mapping[str, float],
) -> Mapping[str, float]:
    """ForecastResult.arc_baseline_stagnation を優先、無ければ s_obs にフォールバック。"""
    out: dict[str, float] = {}
    for arc in arc_index.arcs:
        if arc.edge_id in out:
            continue
        val = forecast_result.arc_baseline_stagnation.get(arc.edge_id)
        if val is None:
            val = s_obs_eff.get(arc.edge_id, 0.0)
        out[arc.edge_id] = float(val)
    return out


def _build_sigma_map(observations: Observations) -> Mapping[str, float]:
    return {s.edge_id: float(s.observed_count) for s in observations.arc_scalar_flows}


def _safe_sum(terms: list):
    """linopy 式のリストの合計。空リストでも壊れないようにする。"""
    if not terms:
        return 0
    total = terms[0]
    for t in terms[1:]:
        total = total + t
    return total
