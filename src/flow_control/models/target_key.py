"""Helpers for the prefixed target keys used in DetectionState.warmup_until_by_target.

Per module design v1 §3.6, warmup target keys are prefixed strings:
- ``node:<node_id>`` for node targets
- ``edge:<edge_id>`` for edge targets
"""

from __future__ import annotations

from .enums import TargetKind


def make_node_key(node_id: str) -> str:
    return f"{TargetKind.NODE.value}:{node_id}"


def make_edge_key(edge_id: str) -> str:
    return f"{TargetKind.EDGE.value}:{edge_id}"


def parse_target_key(key: str) -> tuple[TargetKind, str]:
    prefix, _, ident = key.partition(":")
    if not ident:
        raise ValueError(f"target key missing identifier after prefix: {key!r}")
    if prefix == TargetKind.NODE.value:
        return TargetKind.NODE, ident
    if prefix == TargetKind.EDGE.value:
        return TargetKind.EDGE, ident
    raise ValueError(f"unknown target key prefix in {key!r}")
