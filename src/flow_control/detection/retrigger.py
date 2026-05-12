"""Arc retrigger count maintenance.

Module design v1 §4.7. ``DANGER_FLAG_UP`` triggers are excluded from the
``fired_edges`` set per rule 4 (manual triggers are not counted).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable

from ..models import (
    DetectionState,
    Graph,
    QueuedTrigger,
    QueuedTriggerKind,
    ResolvedConfig,
    RetriggerEntry,
    freeze_retrigger_map,
)


def update_retrigger_counts(
    state: DetectionState,
    normal_triggers: Iterable[QueuedTrigger],
    graph: Graph,
    config: ResolvedConfig,
    server_time: datetime,
) -> DetectionState:
    fired_edges: set[str] = {
        t.origin_edge_id
        for t in normal_triggers
        if t.origin_edge_id is not None and t.kind is not QueuedTriggerKind.DANGER
    }
    in_watch: set[str] = {
        edge_id
        for edge_id, ws in state.arc_watch_states.items()
        if ws.percentile_satisfied or ws.delta_satisfied
    }

    graph_edge_ids = {edge.edge_id for edge in graph.edges}
    disabled_edge_ids = {edge.edge_id for edge in graph.edges if not edge.enabled}

    existing_keys = set(state.arc_retrigger_counts.keys())
    all_keys = existing_keys | fired_edges
    new_counts: dict[str, RetriggerEntry] = {}

    for e in all_keys:
        if e not in graph_edge_ids or e in disabled_edge_ids:
            # 規則3: アーク自体が enabled=false 化された／グラフから削除された
            continue
        entry = state.arc_retrigger_counts.get(e, RetriggerEntry(count=0, quiet_cycles=0, last_fired_at=None))
        fired = e in fired_edges
        watching = e in in_watch
        different_origin_fired = len(fired_edges) > 0 and not fired

        if fired:
            entry = RetriggerEntry(
                count=entry.count + 1,
                quiet_cycles=0,
                last_fired_at=server_time,
            )
        elif different_origin_fired:
            # 規則1: 別アーク発火 → 既存アークのカウントをリセット
            entry = RetriggerEntry(
                count=0,
                quiet_cycles=0,
                last_fired_at=entry.last_fired_at,
            )
        elif not watching:
            new_quiet = entry.quiet_cycles + 1
            if new_quiet >= config.retrigger_reset_quiet_cycles:
                # 規則2: 連続 N サイクル沈静化 → リセット
                entry = RetriggerEntry(
                    count=0,
                    quiet_cycles=0,
                    last_fired_at=entry.last_fired_at,
                )
            else:
                entry = RetriggerEntry(
                    count=entry.count,
                    quiet_cycles=new_quiet,
                    last_fired_at=entry.last_fired_at,
                )
        # それ以外（in_watch かつ未発火・別起点なし）: そのまま維持

        new_counts[e] = entry

    return replace(state, arc_retrigger_counts=freeze_retrigger_map(new_counts))
