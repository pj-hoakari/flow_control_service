"""Normal trigger detection (surge + high stagnation).

Math companion v1 §9.1–§9.3 and module design v1 §4.3 / §4.5.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Mapping

from ..models import (
    ArcWatchState,
    ConfidenceFlag,
    DetectionState,
    Edge,
    Graph,
    HistoryDigest,
    Observations,
    QueuedTrigger,
    QueuedTriggerKind,
    ResolvedConfig,
    TriggerEvidence,
    TriggerSource,
    freeze_watch_map,
)

EPSILON_FLOW = 1e-6


@dataclass(frozen=True)
class TriggerDetectionOutcome:
    """Result of running normal trigger detection.

    ``triggers`` are fresh (not yet queued) triggers produced this cycle.
    ``new_state`` is ``previous_state`` with ``arc_watch_states`` updated.
    """

    triggers: tuple[QueuedTrigger, ...]
    evidences: tuple[TriggerEvidence, ...]
    new_state: DetectionState
    missing_percentile: bool


def detect_normal_triggers(
    graph: Graph,
    observations: Observations,
    history: HistoryDigest,
    state: DetectionState,
    config: ResolvedConfig,
    degraded: bool,
    server_time: datetime,
) -> TriggerDetectionOutcome:
    triggers: list[QueuedTrigger] = []
    evidences: list[TriggerEvidence] = []
    new_watch: dict[str, ArcWatchState] = dict(state.arc_watch_states)
    missing_percentile = False

    for edge in graph.edges:
        if not edge.enabled:
            new_watch.pop(edge.edge_id, None)
            continue

        surge_evidence = _evaluate_surge(edge, history, config, server_time)
        if surge_evidence is not None:
            triggers.append(
                QueuedTrigger(
                    kind=QueuedTriggerKind.SURGE,
                    first_fired_at=server_time,
                    last_fired_at=server_time,
                    accumulated_score=1.0,
                    snapshot_ref=observations.observed_at.isoformat(),
                    origin_edge_id=edge.edge_id,
                )
            )
            evidences.append(surge_evidence)

        hs_outcome = _evaluate_high_stagnation(
            edge=edge,
            observations=observations,
            history=history,
            previous_watch=state.arc_watch_states.get(edge.edge_id),
            config=config,
            degraded=degraded,
            server_time=server_time,
        )

        if hs_outcome.missing_percentile:
            missing_percentile = True

        if hs_outcome.new_watch is None:
            new_watch.pop(edge.edge_id, None)
        else:
            new_watch[edge.edge_id] = hs_outcome.new_watch

        if hs_outcome.fired_evidence is not None:
            triggers.append(
                QueuedTrigger(
                    kind=QueuedTriggerKind.HIGH_STAGNATION,
                    first_fired_at=hs_outcome.new_watch.started_at if hs_outcome.new_watch else server_time,
                    last_fired_at=server_time,
                    accumulated_score=1.0,
                    snapshot_ref=observations.observed_at.isoformat(),
                    origin_edge_id=edge.edge_id,
                )
            )
            evidences.append(hs_outcome.fired_evidence)

    new_state = replace(state, arc_watch_states=freeze_watch_map(new_watch))
    return TriggerDetectionOutcome(
        triggers=tuple(triggers),
        evidences=tuple(evidences),
        new_state=new_state,
        missing_percentile=missing_percentile,
    )


def _evaluate_surge(
    edge: Edge,
    history: HistoryDigest,
    config: ResolvedConfig,
    server_time: datetime,
) -> TriggerEvidence | None:
    window = history.window_for(edge.edge_id)
    if window is None or len(window.samples) < 2:
        return None

    window_minutes = 30 + (edge.time_resolution_s / 60.0)
    cutoff = server_time - timedelta(minutes=window_minutes)
    samples = [(t, v) for (t, v) in window.samples if t >= cutoff]
    if len(samples) < 2:
        return None

    # 時間軸を分換算した最小二乗回帰で傾きを求める
    t0 = samples[0][0]
    xs = [(t - t0).total_seconds() / 60.0 for (t, _) in samples]
    ys = [v for (_, v) in samples]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den < EPSILON_FLOW:
        return None
    slope = num / den
    if mean_y < EPSILON_FLOW:
        return None
    rate_percent = (slope / mean_y) * 100.0
    threshold = config.surge_rate_threshold_percent_per_min
    if rate_percent > threshold:
        return TriggerEvidence(
            source=TriggerSource.SURGE,
            occurred_at=server_time,
            edge_id=edge.edge_id,
            metric_value=rate_percent,
            threshold_value=threshold,
        )
    return None


@dataclass(frozen=True)
class _HighStagnationOutcome:
    new_watch: ArcWatchState | None
    fired_evidence: TriggerEvidence | None
    missing_percentile: bool


def _evaluate_high_stagnation(
    edge: Edge,
    observations: Observations,
    history: HistoryDigest,
    previous_watch: ArcWatchState | None,
    config: ResolvedConfig,
    degraded: bool,
    server_time: datetime,
) -> _HighStagnationOutcome:
    stag = observations.stagnation_for(edge.edge_id)
    if stag is None or stag.confidence_flag is ConfidenceFlag.INVALID:
        return _HighStagnationOutcome(new_watch=None, fired_evidence=None, missing_percentile=False)

    stat = history.stat_for(edge.edge_id)
    p90 = stat.p90_stagnation if stat is not None else None
    baseline = stat.baseline_stagnation if stat is not None else None

    # b.1 (percentile) と b.2 (delta) の判定
    b1_effective: bool
    missing_percentile = False
    if degraded or p90 is None:
        b1_effective = True
        if p90 is None:
            missing_percentile = True
    else:
        b1_effective = stag.stagnation >= p90

    if baseline is None:
        b2 = False
    else:
        b2 = (stag.stagnation - baseline) >= config.beta

    # 警戒状態に保存する旗は「実際に判定可能だった条件」のままにする
    if degraded or p90 is None:
        b1_for_state = False if not b2 else True  # 縮退モードでは b.1 を実観測しないので b2 と同値扱い
    else:
        b1_for_state = stag.stagnation >= p90

    if b1_effective and b2:
        if (
            previous_watch is not None
            and previous_watch.percentile_satisfied
            and previous_watch.delta_satisfied
            and previous_watch.started_at is not None
        ):
            started_at = previous_watch.started_at
        else:
            started_at = server_time
        new_watch = ArcWatchState(
            edge_id=edge.edge_id,
            percentile_satisfied=True,
            delta_satisfied=True,
            started_at=started_at,
        )
        duration = server_time - started_at
        if duration >= timedelta(minutes=config.high_stagnation_duration_min):
            evidence = TriggerEvidence(
                source=TriggerSource.HIGH_STAGNATION,
                occurred_at=server_time,
                edge_id=edge.edge_id,
                metric_value=stag.stagnation,
                threshold_value=p90 if (p90 is not None and not degraded) else baseline,
                duration_min=duration.total_seconds() / 60.0,
            )
            return _HighStagnationOutcome(
                new_watch=new_watch,
                fired_evidence=evidence,
                missing_percentile=missing_percentile,
            )
        return _HighStagnationOutcome(
            new_watch=new_watch,
            fired_evidence=None,
            missing_percentile=missing_percentile,
        )

    if b1_for_state or b2:
        new_watch = ArcWatchState(
            edge_id=edge.edge_id,
            percentile_satisfied=b1_for_state,
            delta_satisfied=b2,
            started_at=None,
        )
        return _HighStagnationOutcome(
            new_watch=new_watch,
            fired_evidence=None,
            missing_percentile=missing_percentile,
        )

    return _HighStagnationOutcome(
        new_watch=None,
        fired_evidence=None,
        missing_percentile=missing_percentile,
    )
