from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import ClassVar

from ..domain import EdgeID, NodeID


class EvidenceSource(str, Enum):
    SURGE = "SURGE"
    HIGH_STAGNATION = "HIGH_STAGNATION"
    DANGER = "DANGER"
    QUEUE_SCORE = "QUEUE_SCORE"
    QUEUE_DIVERSITY = "QUEUE_DIVERSITY"


@dataclass(frozen=True)
class SurgeEvidence:
    source: ClassVar[EvidenceSource] = EvidenceSource.SURGE
    edge_id: EdgeID
    occurred_at: datetime
    rate_percent_per_min: float  # 観測変化率 %/分
    threshold_percent_per_min: float


@dataclass(frozen=True)
class HighStagnationEvidence:
    source: ClassVar[EvidenceSource] = EvidenceSource.HIGH_STAGNATION
    edge_id: EdgeID
    occurred_at: datetime
    stagnation: float  # 観測停滞量
    percentile_threshold: float  # p90 停滞量
    duration_min: float  # 発火に要した継続時間 M 分


@dataclass(frozen=True)
class DangerEvidence:
    source: ClassVar[EvidenceSource] = EvidenceSource.DANGER
    occurred_at: datetime
    edge_id: EdgeID | None = None
    node_id: NodeID | None = None


@dataclass(frozen=True)
class QueueScoreEvidence:
    source: ClassVar[EvidenceSource] = EvidenceSource.QUEUE_SCORE
    occurred_at: datetime
    accumulated_score: float  # キュー内の蓄積スコア合計
    score_threshold: float


@dataclass(frozen=True)
class QueueDiversityEvidence:
    source: ClassVar[EvidenceSource] = EvidenceSource.QUEUE_DIVERSITY
    occurred_at: datetime
    distinct_origin_count: int  # キュー内の異なる起点アーク数
    diversity_threshold: int


TriggerEvidence = (
    SurgeEvidence
    | HighStagnationEvidence
    | DangerEvidence
    | QueueScoreEvidence
    | QueueDiversityEvidence
)
