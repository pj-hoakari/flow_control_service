"""Resolved configuration (module design v1 §3.10).

Only Detection-relevant fields are implemented at this stage. Other module
fields (Forecasting / Detour / Optimization / extension flags) should be added
alongside their respective module implementations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedConfig:
    surge_rate_threshold_percent_per_min: float
    high_stagnation_duration_min: float
    beta: float
    cooldown_duration_min: float
    warmup_duration_min: float
    retrigger_warning_threshold: int = 3
    retrigger_reset_quiet_cycles: int = 3
    queue_score_threshold: float = float("inf")
    queue_diversity_threshold: int = 2147483647
