"""Tenant context (module design v1 §3.2)."""

from __future__ import annotations

from dataclasses import dataclass

from .enums import TenantCategory


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    tenant_category: TenantCategory
    available_history_hours: float
