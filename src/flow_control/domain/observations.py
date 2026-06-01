from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .enums import FlowDirection
from .graph import EdgeID, NodeID


class ConfidenceFlag(str, Enum):
    OK = "OK"
    HOLD = "HOLD"  # 直近有効値HOLD状態 低信頼度
    INVALID = "INVALID"  # 観測不能


@dataclass(frozen=True)
class ArcFlow:
    edge_id: EdgeID
    direction: FlowDirection
    flow_rate: float
    confidence_flag: ConfidenceFlag = ConfidenceFlag.OK


@dataclass(frozen=True)
class ArcStagnation:
    edge_id: EdgeID
    stagnation: float
    confidence_flag: ConfidenceFlag = ConfidenceFlag.OK


@dataclass(frozen=True)
class ArcScalarFlow:
    edge_id: EdgeID
    observed_count: float
    confidence_flag: ConfidenceFlag = ConfidenceFlag.OK


@dataclass(frozen=True)
class NodeOccupancy:
    node_id: NodeID
    occupancy: float
    confidence_flag: ConfidenceFlag = ConfidenceFlag.OK


@dataclass(frozen=True)
class Observations:
    observed_at: datetime
    snapshot_ref: str | None = None
    arc_flows: tuple[ArcFlow, ...] = field(default_factory=tuple)
    arc_stagnations: tuple[ArcStagnation, ...] = field(default_factory=tuple)
    arc_scalar_flows: tuple[ArcScalarFlow, ...] = field(default_factory=tuple)
    node_occupancies: tuple[NodeOccupancy, ...] = field(default_factory=tuple)

    def stagnation_of(self, edge_id: EdgeID) -> ArcStagnation | None:
        for arc_stagnation in self.arc_stagnations:
            if arc_stagnation.edge_id == edge_id:
                return arc_stagnation
        return None

    def scalar_flow_of(self, edge_id: EdgeID) -> ArcScalarFlow | None:
        for arc_scalar_flow in self.arc_scalar_flows:
            if arc_scalar_flow.edge_id == edge_id:
                return arc_scalar_flow
        return None
