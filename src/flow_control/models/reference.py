"""Reference (cold-start fallback) values (module design v1 §3.7)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ThresholdSet:
    surge_rate_threshold_percent_per_min: float = 0.0
    high_stagnation_duration_min: float = 0.0
    beta: float = 0.0


@dataclass(frozen=True)
class ThresholdDefaults:
    short_term: ThresholdSet = field(default_factory=ThresholdSet)
    long_term: ThresholdSet = field(default_factory=ThresholdSet)


@dataclass(frozen=True)
class TagReference:
    attribute_tag: str
    eta_typical: float | None = None
    baseline_stagnation: float | None = None
    sample_count: int = 0


@dataclass(frozen=True)
class Reference:
    by_attribute_tag: tuple[TagReference, ...] = ()
    default_thresholds: ThresholdDefaults = field(default_factory=ThresholdDefaults)
    source_k_anonymity: int = 0
