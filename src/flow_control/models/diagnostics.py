"""Trigger evidence records (module design v1 §3.13)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .enums import TriggerSource


@dataclass(frozen=True)
class TriggerEvidence:
    source: TriggerSource
    occurred_at: datetime
    edge_id: str | None = None
    node_id: str | None = None
    metric_value: float | None = None
    threshold_value: float | None = None
    duration_min: float | None = None
