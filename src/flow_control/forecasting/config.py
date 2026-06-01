from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedConfig:
    min_reference_sample_count: int
    fallback_eta: float
    gravity_alpha: float = 1.0
