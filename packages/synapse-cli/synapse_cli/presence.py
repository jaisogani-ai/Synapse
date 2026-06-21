# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Simple presence — ``online`` / ``busy`` / ``offline``.

No CRDT, no gossip, no leader election. A receiver advertises its current
status by serving ``GET /presence`` (handled inside :class:`transport.A2AServer`).
The sender's :func:`probe` does an HTTP GET on the receiver's presence URL.

The local "what status am I?" lives in a single-row JSON file at
``$SYNAPSE_HOME/presence.json`` so the operator can flip it manually.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ONLINE = "online"
BUSY = "busy"
OFFLINE = "offline"

#: All status values the API accepts.
VALID_STATUS = frozenset({ONLINE, BUSY, OFFLINE})


@dataclass(frozen=True)
class PresenceSnapshot:
    agent_id: str
    status: str
    endpoint: str
    checked_at: str
    reachable: bool


class LocalPresence:
    """Operator-controlled presence state for *this* daemon."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get(self) -> str:
        if not self._path.exists():
            return ONLINE
        try:
            return str(json.loads(self._path.read_text()).get("status", ONLINE))
        except (json.JSONDecodeError, OSError):
            return ONLINE

    def set(self, status: str) -> None:
        if status not in VALID_STATUS:
            raise ValueError(f"status must be one of {sorted(VALID_STATUS)}")
        self._path.write_text(
            json.dumps({"status": status, "at": _now_iso()}, sort_keys=True)
        )


def probe(agent_id: str, endpoint_url: str, timeout: float = 1.0) -> PresenceSnapshot:
    """Return a one-shot snapshot of ``agent_id``'s remote presence.

    The endpoint URL is the A2A handler URL (e.g. ``.../a2a``); we strip
    ``/a2a`` to find the receiver's presence path.
    """
    base = endpoint_url[:-4] if endpoint_url.endswith("/a2a") else endpoint_url.rstrip("/")
    presence_url = f"{base}/presence"
    try:
        with urllib.request.urlopen(presence_url, timeout=timeout) as resp:
            body = resp.read()
            status = str(json.loads(body).get("status", OFFLINE))
            reachable = True
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError,
            json.JSONDecodeError):
        status = OFFLINE
        reachable = False
    return PresenceSnapshot(
        agent_id=agent_id,
        status=status,
        endpoint=endpoint_url,
        checked_at=_now_iso(),
        reachable=reachable,
    )


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
