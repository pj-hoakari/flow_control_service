"""Public ``detect`` entry point for the Detection module (module design v1 §4)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from ..models import (
    DetectionState,
    Event,
    Graph,
    HistoryDigest,
    Observations,
    QueuedTrigger,
    Reference,
    ResolvedConfig,
    TenantCategory,
    TenantContext,
    TriggerEvidence,
    VerdictHint,
)
from .cooldown import (
    clear_queue,
    in_cooldown,
    queue_exceeds_score,
    queue_is_diverse,
    queue_push,
)
from .events import apply_events
from .retrigger import update_retrigger_counts
from .snapshot import effective_snapshot
from .triggers import detect_normal_triggers
from .warmup import all_targets_in_warmup


SHORT_TENANT_HISTORY_THRESHOLD_HOURS = 4.0


@dataclass(frozen=True)
class ModeFlags:
    degraded_short_tenant: bool
    missing_percentile: bool


@dataclass(frozen=True)
class DetectionResult:
    """Outcome of a Detection step run.

    ``effective_snapshot`` is, in this PoC, always the request's
    ``observations`` even when firing from queue — see ``detection.snapshot``
    for the rationale.
    """

    verdict_hint: VerdictHint
    triggered_edges: tuple[str, ...]
    effective_snapshot: Observations
    new_state: DetectionState
    mode_flags: ModeFlags
    evidences: tuple[TriggerEvidence, ...]


def detect(
    graph: Graph,
    observations: Observations,
    history_digest: HistoryDigest,
    previous_state: DetectionState,
    events: tuple[Event, ...] | list[Event],
    references: Reference,
    tenant_context: TenantContext,
    config: ResolvedConfig,
    server_time: datetime,
) -> DetectionResult:
    """Run the Detection step.

    This is a pure function: it never reads system time, never performs I/O,
    and never mutates inputs. The ``previous_state`` is treated as immutable;
    the returned ``DetectionResult.new_state`` is the value the orchestrator
    should persist for the next request.

    ``references`` is currently unused by Detection but is accepted in the
    signature so that the public surface matches the module-design contract
    once Forecasting starts consuming it.
    """
    del references  # 現状の Detection 実装では参照値を直接使わない

    # 1. apply_events
    state, danger_triggers, danger_evidences = apply_events(
        previous_state, events, graph, config, server_time
    )

    # 2. degraded mode flag
    degraded = (
        tenant_context.tenant_category is TenantCategory.SHORT_TERM
        or tenant_context.available_history_hours < SHORT_TENANT_HISTORY_THRESHOLD_HOURS
    )

    # 3. ウォームアップ判定
    if not danger_triggers and all_targets_in_warmup(state, graph, server_time):
        state = update_retrigger_counts(state, [], graph, config, server_time)
        return DetectionResult(
            verdict_hint=VerdictHint.SKIPPED_WARMUP,
            triggered_edges=(),
            effective_snapshot=effective_snapshot(observations),
            new_state=state,
            mode_flags=ModeFlags(
                degraded_short_tenant=degraded,
                missing_percentile=False,
            ),
            evidences=(),
        )

    # 4. 通常トリガー検出
    outcome = detect_normal_triggers(
        graph=graph,
        observations=observations,
        history=history_digest,
        state=state,
        config=config,
        degraded=degraded,
        server_time=server_time,
    )
    state = outcome.new_state
    normal_triggers = list(outcome.triggers)
    evidences: list[TriggerEvidence] = list(danger_evidences) + list(outcome.evidences)
    mode_flags = ModeFlags(
        degraded_short_tenant=degraded,
        missing_percentile=outcome.missing_percentile,
    )

    cooling = in_cooldown(state, server_time)
    if cooling:
        if danger_triggers:
            return _fire(
                state=state,
                danger_triggers=danger_triggers,
                normal_triggers=normal_triggers,
                observations=observations,
                evidences=evidences,
                graph=graph,
                config=config,
                server_time=server_time,
                mode_flags=mode_flags,
            )
        if normal_triggers:
            state = queue_push(state, normal_triggers, observations, server_time)
            if queue_exceeds_score(state, config) or queue_is_diverse(state, config):
                return _fire_from_queue(
                    state=state,
                    observations=observations,
                    evidences=evidences,
                    graph=graph,
                    config=config,
                    server_time=server_time,
                    mode_flags=mode_flags,
                )
            state = update_retrigger_counts(state, normal_triggers, graph, config, server_time)
            return DetectionResult(
                verdict_hint=VerdictHint.QUEUED,
                triggered_edges=(),
                effective_snapshot=effective_snapshot(observations),
                new_state=state,
                mode_flags=mode_flags,
                evidences=tuple(evidences),
            )
        state = update_retrigger_counts(state, [], graph, config, server_time)
        return DetectionResult(
            verdict_hint=VerdictHint.SKIPPED_COOLDOWN,
            triggered_edges=(),
            effective_snapshot=effective_snapshot(observations),
            new_state=state,
            mode_flags=mode_flags,
            evidences=tuple(evidences),
        )

    # out of cooldown
    if danger_triggers or normal_triggers:
        return _fire(
            state=state,
            danger_triggers=danger_triggers,
            normal_triggers=normal_triggers,
            observations=observations,
            evidences=evidences,
            graph=graph,
            config=config,
            server_time=server_time,
            mode_flags=mode_flags,
        )

    state = update_retrigger_counts(state, [], graph, config, server_time)
    return DetectionResult(
        verdict_hint=VerdictHint.NO_TRIGGER,
        triggered_edges=(),
        effective_snapshot=effective_snapshot(observations),
        new_state=state,
        mode_flags=mode_flags,
        evidences=tuple(evidences),
    )


def _fire(
    state: DetectionState,
    danger_triggers: list[QueuedTrigger],
    normal_triggers: list[QueuedTrigger],
    observations: Observations,
    evidences: list[TriggerEvidence],
    graph: Graph,
    config: ResolvedConfig,
    server_time: datetime,
    mode_flags: ModeFlags,
) -> DetectionResult:
    triggered_edges = _unique_edge_ids(danger_triggers + normal_triggers)
    state = update_retrigger_counts(state, normal_triggers, graph, config, server_time)
    state = replace(
        state,
        cooldown_until=server_time + timedelta(minutes=config.cooldown_duration_min),
        consecutive_skip_count=0,
    )
    state = clear_queue(state)
    return DetectionResult(
        verdict_hint=VerdictHint.TRIGGERED,
        triggered_edges=triggered_edges,
        effective_snapshot=effective_snapshot(observations),
        new_state=state,
        mode_flags=mode_flags,
        evidences=tuple(evidences),
    )


def _fire_from_queue(
    state: DetectionState,
    observations: Observations,
    evidences: list[TriggerEvidence],
    graph: Graph,
    config: ResolvedConfig,
    server_time: datetime,
    mode_flags: ModeFlags,
) -> DetectionResult:
    queued_edges = _unique_edge_ids(state.trigger_queue)
    # キュー駆動発火における正規のトリガー一覧は queue 内容そのもの
    fired_from_queue = list(state.trigger_queue)
    state = update_retrigger_counts(state, fired_from_queue, graph, config, server_time)
    state = replace(
        state,
        cooldown_until=server_time + timedelta(minutes=config.cooldown_duration_min),
        consecutive_skip_count=0,
    )
    state = clear_queue(state)
    return DetectionResult(
        verdict_hint=VerdictHint.TRIGGERED,
        triggered_edges=queued_edges,
        effective_snapshot=effective_snapshot(observations),
        new_state=state,
        mode_flags=mode_flags,
        evidences=tuple(evidences),
    )


def _unique_edge_ids(triggers) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for t in triggers:
        if t.origin_edge_id is not None and t.origin_edge_id not in seen:
            seen[t.origin_edge_id] = None
    return tuple(seen.keys())
