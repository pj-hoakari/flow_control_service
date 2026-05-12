"""Effective snapshot selection for the optimization downstream.

Module design v1 §4.2 / requirements v1 §4.3 :「クールタイム解除時はキュー最後の
発火時点のスナップショットを採用」。``QueuedTrigger.snapshot_ref`` is just an
opaque identifier in the stateless contract, so within this PoC we always
return the request's current ``observations``. The hook is kept as a separate
function so that the RequestHandler-level reinjection of past snapshots can be
plugged in later without changing call sites.
"""

from __future__ import annotations

from ..models import Observations


def effective_snapshot(current: Observations) -> Observations:
    return current
