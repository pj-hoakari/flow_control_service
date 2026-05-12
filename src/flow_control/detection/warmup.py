"""Warmup window evaluation.

Module design v1 §4.4 / §3.6: warmup_until_by_target uses prefix-encoded keys
(``node:<id>`` / ``edge:<id>``).
"""

from __future__ import annotations

from datetime import datetime

from ..models import DetectionState, Graph, make_edge_key, make_node_key


def all_targets_in_warmup(
    state: DetectionState,
    graph: Graph,
    server_time: datetime,
) -> bool:
    """Return True iff every enabled node/edge is still within warmup at ``server_time``.

    Returns False when there are no enabled targets at all (so we never block
    detection just because the graph is empty).
    """
    keys: list[str] = []
    for node in graph.nodes:
        if node.enabled:
            keys.append(make_node_key(node.node_id))
    for edge in graph.edges:
        if edge.enabled:
            keys.append(make_edge_key(edge.edge_id))
    if not keys:
        return False
    for key in keys:
        until = state.warmup_until_by_target.get(key)
        if until is None or server_time >= until:
            return False
    return True
