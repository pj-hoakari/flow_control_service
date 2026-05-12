"""Manual intervention / schedule events (module design v1 §3.9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from .enums import EventKind


def _empty_params() -> Mapping[str, Any]:
    return MappingProxyType({})


@dataclass(frozen=True)
class Event:
    kind: EventKind
    target_id: str
    occurred_at: datetime
    params: Mapping[str, Any] = field(default_factory=_empty_params)
