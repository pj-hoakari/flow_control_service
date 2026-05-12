from dataclasses import dataclass
from datetime import datetime

from ..domain import EdgeID, Graph
from .history import HistoryDigest
from .observations import Observations
from .state import DetectionState


@dataclass(frozen=True)
class NormalTriggerDetectionResult:
    triggered_edges: tuple[EdgeID, ...]
    new_state: DetectionState


def detect_normal_triggers(
    graph: Graph,
    observations: Observations,
    history_digest: HistoryDigest,
    previous_state: DetectionState,
    server_time: datetime,
) -> NormalTriggerDetectionResult:
    # TODO: impl
    return NormalTriggerDetectionResult(triggered_edges=(), new_state=previous_state)
