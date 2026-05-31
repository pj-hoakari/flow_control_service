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
