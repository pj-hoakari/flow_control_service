from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedConfig:
    surge_rate_threshold_percent_per_min: float
