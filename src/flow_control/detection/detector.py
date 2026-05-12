from dataclasses import dataclass
from datetime import datetime

from ..domain.graph import EdgeID, Graph
from .history import HistoryDigest
from .observations import Observations
from .state import DetectionState


@dataclass(frozen=True)
class DetectionResult:
    triggered_edges: tuple[EdgeID, ...]
    new_state: DetectionState


def detect(
    graph: Graph,
    previous_state: DetectionState,
    observations: Observations,
    history_digest: HistoryDigest,
    server_time: datetime,
) -> DetectionResult:

    # TODO: Impl
    return DetectionResult(
        triggered_edges=(),
        new_state=previous_state,
    )
