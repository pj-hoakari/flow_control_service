"""Optimization module — 2-phase lexicographic MILP (module design v1 §7, math companion §11)."""

from .api import OptimizeResult, optimize
from .arc_index import ArcIndex, DirectedArc, build_arc_index

__all__ = [
    "ArcIndex",
    "DirectedArc",
    "OptimizeResult",
    "build_arc_index",
    "optimize",
]
