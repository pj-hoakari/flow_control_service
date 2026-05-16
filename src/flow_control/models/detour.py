"""DetourRouting outputs consumed by the Optimization module (module design v1 §6, math companion §12)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Path:
    edge_ids: tuple[str, ...]
    total_length: float = 0.0
    contains_trigger: bool = False


@dataclass(frozen=True)
class DetourSet:
    origin_edge_id: str
    endpoint_pair: tuple[str, str]
    paths: tuple[Path, ...] = ()
    k_effective: int = 0


@dataclass(frozen=True)
class DetourResult:
    detour_sets: tuple[DetourSet, ...] = ()

    def all_path_edge_ids(self) -> frozenset[str]:
        """Edges forming P_trigger for the Phase 2 throughput objective (math companion §11.4.2)."""
        ids: set[str] = set()
        for s in self.detour_sets:
            ids.add(s.origin_edge_id)
            for p in s.paths:
                ids.update(p.edge_ids)
        return frozenset(ids)
