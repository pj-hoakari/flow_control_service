"""Forecasting outputs consumed by the Optimization module (module design v1 §5.2, math companion §10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


def _empty_float_map() -> Mapping[str, float]:
    return MappingProxyType({})


def _empty_int_map() -> Mapping[str, int]:
    return MappingProxyType({})


@dataclass(frozen=True)
class Commodity:
    """OD commodity k = (origin, destination, demand) — math companion §10.3."""

    origin_node_id: str
    destination_node_id: str
    demand: float


@dataclass(frozen=True)
class FallbackReport:
    used_reference_edges: tuple[str, ...] = ()
    used_default_edges: tuple[str, ...] = ()
    reference_sample_counts: Mapping[str, int] = field(default_factory=_empty_int_map)


@dataclass(frozen=True)
class ForecastResult:
    """Output of the Forecasting Step (module design v1 §5.2).

    `arc_baseline_stagnation` は本来 HistoryDigest 由来 (math companion §11.3 の s_bar_a) だが、
    optimize() の純粋関数シグネチャから history_digest を切り離すため、Forecasting Step が
    history_digest から派生させて持ち回す形にしている。値が欠損したアークについては
    s_obs_a (現在観測値) をフォールバックとして使用する。
    """

    commodities: tuple[Commodity, ...] = ()
    node_confidence: Mapping[str, float] = field(default_factory=_empty_float_map)
    arc_flow_sensitivity: Mapping[str, float] = field(default_factory=_empty_float_map)
    arc_baseline_stagnation: Mapping[str, float] = field(default_factory=_empty_float_map)
    fallback_usage: FallbackReport = field(default_factory=FallbackReport)


def freeze_float_map(d: Mapping[str, float]) -> Mapping[str, float]:
    return MappingProxyType(dict(d))


def freeze_int_map(d: Mapping[str, int]) -> Mapping[str, int]:
    return MappingProxyType(dict(d))
