from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedConfig:
    min_reference_sample_count: int
    fallback_eta: float
    gravity_alpha: float = 1.0  # 距離減衰指数 α
    delta_min: float = 0.5  # OD 量カット δ_min
