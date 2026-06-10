from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedConfig:
    surge_rate_threshold_percent_per_min: float
    surge_evaluate_window_minute: float = 30.0
    high_stagnation_duration_min: float = 5.0
    beta: float = 1.0

    cooldown_duration_min: float = 60.0
    queue_score_threshold: float = 5.0
    queue_diversity_threshold: int = 3
    # キュー統合発火の鮮度ガード X 分
    # None なら cooldown_duration_min / 2 を使用
    queue_freshness_min: float | None = None

    warmup_duration_min: float = 60.0

    retrigger_warning_threshold: int = 3
    retrigger_reset_quiet_cycles: int = 3
    max_consecutive_skips: int = 3
