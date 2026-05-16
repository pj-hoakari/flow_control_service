"""Resolved configuration (module design v1 §3.10).

Detection / Optimization 用フィールドのみ実装している。他モジュール
（Forecasting / Detour / 拡張ロードマップ連動フラグ）のフィールドは、
それぞれの実装と同時に追加する想定。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedConfig:
    # ── Detection Step ────────────────────────────
    surge_rate_threshold_percent_per_min: float
    high_stagnation_duration_min: float
    beta: float
    cooldown_duration_min: float
    warmup_duration_min: float
    retrigger_warning_threshold: int = 3
    retrigger_reset_quiet_cycles: int = 3
    queue_score_threshold: float = float("inf")
    queue_diversity_threshold: int = 2147483647

    # ── Optimization Step (math companion §8.3 / module design §3.10) ──
    throughput_target_edges: tuple[str, ...] = ()
    milp_time_limit_sec: float = 600.0
    solver_seed: int = 0
    epsilon: float = 1e-3
    epsilon_0: float = 1e-6
    big_m_factor: float = 1.0
    delta_min: float = 0.5
