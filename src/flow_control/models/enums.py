"""Enumerations used across the flow control service."""

from __future__ import annotations

from enum import Enum


class NodeKind(str, Enum):
    GOAL = "GOAL"
    GOAL_TRANSIT_MIXED = "GOAL_TRANSIT_MIXED"


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


class ConfidenceFlag(str, Enum):
    OK = "OK"
    HOLD = "HOLD"
    INVALID = "INVALID"


class TenantCategory(str, Enum):
    SHORT_TERM = "SHORT_TERM"
    LONG_TERM = "LONG_TERM"


class EventKind(str, Enum):
    DANGER_FLAG_UP = "DANGER_FLAG_UP"
    DANGER_FLAG_DOWN = "DANGER_FLAG_DOWN"
    DIRECTION_SWITCH = "DIRECTION_SWITCH"
    ADD_EDGE = "ADD_EDGE"
    ADD_NODE = "ADD_NODE"
    DISABLE = "DISABLE"
    ENABLE = "ENABLE"
    SCHEDULED_INFLOW = "SCHEDULED_INFLOW"
    SCHEDULED_ATTR_CHANGE = "SCHEDULED_ATTR_CHANGE"


class QueuedTriggerKind(str, Enum):
    SURGE = "SURGE"
    HIGH_STAGNATION = "HIGH_STAGNATION"
    DANGER = "DANGER"


class VerdictHint(str, Enum):
    TRIGGERED = "TRIGGERED"
    QUEUED = "QUEUED"
    SKIPPED_COOLDOWN = "SKIPPED_COOLDOWN"
    SKIPPED_WARMUP = "SKIPPED_WARMUP"
    NO_TRIGGER = "NO_TRIGGER"


class TriggerSource(str, Enum):
    SURGE = "SURGE"
    HIGH_STAGNATION = "HIGH_STAGNATION"
    DANGER = "DANGER"
    QUEUE_SCORE = "QUEUE_SCORE"
    QUEUE_DIVERSITY = "QUEUE_DIVERSITY"


class TargetKind(str, Enum):
    NODE = "node"
    EDGE = "edge"
