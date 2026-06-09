"""Domain enums describing graph elements"""

from __future__ import annotations

from enum import Enum


class NodeKind(str, Enum):
    GOAL = "GOAL"
    GOAL_TRANSIT_MIXED = "GOAL_TRANSIT_MIXED"
    TRANSIT_ONLY = "TRANSIT_ONLY"


class DirectionConstraint(str, Enum):
    BIDIRECTIONAL_PRIOR = "BIDIRECTIONAL_PRIOR"
    ONEWAY_A_TO_B_PRIOR = "ONEWAY_A_TO_B_PRIOR"
    ONEWAY_B_TO_A_PRIOR = "ONEWAY_B_TO_A_PRIOR"
    LEGAL_FIXED_A_TO_B = "LEGAL_FIXED_A_TO_B"
    LEGAL_FIXED_B_TO_A = "LEGAL_FIXED_B_TO_A"
    LEGAL_FIXED_BIDIRECTIONAL = "LEGAL_FIXED_BIDIRECTIONAL"


class CurrentDirection(str, Enum):
    A_TO_B = "A_TO_B"
    B_TO_A = "B_TO_A"
    BIDIRECTIONAL = "BIDIRECTIONAL"


class ObservationType(str, Enum):
    VECTOR = "VECTOR"
    SCALAR = "SCALAR"


class FlowDirection(str, Enum):
    A_TO_B = "A_TO_B"
    B_TO_A = "B_TO_A"
