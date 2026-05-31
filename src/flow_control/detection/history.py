from dataclasses import dataclass, field
from datetime import datetime

from ..domain.graph import EdgeID


@dataclass(frozen=True)
class ArcHistoryStat:
    edge_id: EdgeID
    p90_stagnation: float | None = None
    baseline_stagnation: float | None = None


@dataclass(frozen=True)
class ArcWindowSeries:
    edge_id: EdgeID
    samples: tuple[tuple[datetime, float], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HistoryDigest:
    arc_stats: tuple[ArcHistoryStat, ...] = field(default_factory=tuple)
    window_series: tuple[ArcWindowSeries, ...] = field(default_factory=tuple)
    completeness: float = 0.0

    def stat_of(self, edge_id: EdgeID) -> ArcHistoryStat | None:
        for stat in self.arc_stats:
            if stat.edge_id == edge_id:
                return stat
        return None

    def window_series_of(self, edge_id: EdgeID) -> ArcWindowSeries | None:
        for series in self.window_series:
            if series.edge_id == edge_id:
                return series
        return None
