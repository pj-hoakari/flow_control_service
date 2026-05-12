"""History digest (module design v1 §3.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ArcHistoryStat:
    edge_id: str
    p90_stagnation: float | None = None
    baseline_stagnation: float | None = None
    flow_sensitivity_eta: float | None = None
    available_span_hours: float = 0.0


@dataclass(frozen=True)
class ArcWindowSeries:
    edge_id: str
    samples: tuple[tuple[datetime, float], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HistoryDigest:
    arc_stats: tuple[ArcHistoryStat, ...] = field(default_factory=tuple)
    window_series: tuple[ArcWindowSeries, ...] = field(default_factory=tuple)
    completeness: float = 0.0

    def stat_for(self, edge_id: str) -> ArcHistoryStat | None:
        for s in self.arc_stats:
            if s.edge_id == edge_id:
                return s
        return None

    def window_for(self, edge_id: str) -> ArcWindowSeries | None:
        for w in self.window_series:
            if w.edge_id == edge_id:
                return w
        return None
