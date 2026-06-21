# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Quarantine policy — auto-reject messages from agents whose reputation
has fallen below the quarantine threshold.

This is the v0.1.0-alpha implementation of the "Automatic Quarantine"
behaviour: when a sender's reputation drops to the quarantine threshold
(default 0.1) the receiver rejects all inbound messages until the operator
explicitly releases the quarantine, or the sender's reputation climbs back
above the threshold.

The policy is intentionally simple — a per-agent flag plus a numeric
floor. There is no ML model. There is no time-decay logic. It exists so
that a clearly-bad sender stops eating receiver CPU and inbox rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

#: Reputation at or below this score → automatic quarantine.
DEFAULT_QUARANTINE_THRESHOLD = 0.1


@dataclass(frozen=True)
class QuarantineEntry:
    """One quarantined agent's reason + when it was applied."""

    agent_id: str
    reason: str
    at: str  # ISO-8601


class QuarantineStore:
    """JSON-backed per-agent quarantine set.

    The store is small on purpose: a flat ``agent_id -> {reason, at}`` map.
    Reading the file is the source of truth; ``is_quarantined`` re-reads
    on each call so an operator's manual edit (e.g. removing a line) takes
    effect without restarting the receiver.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict[str, str]]:
        if not self._path.exists():
            return {}
        try:
            return dict(json.loads(self._path.read_text()))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, dict[str, str]]) -> None:
        self._path.write_text(json.dumps(data, indent=2, sort_keys=True))

    def is_quarantined(self, agent_id: str) -> bool:
        return agent_id in self._load()

    def quarantine(self, agent_id: str, reason: str, at: str) -> QuarantineEntry:
        data = self._load()
        entry = {"reason": reason, "at": at}
        data[agent_id] = entry
        self._save(data)
        return QuarantineEntry(agent_id=agent_id, reason=reason, at=at)

    def release(self, agent_id: str) -> bool:
        data = self._load()
        if agent_id not in data:
            return False
        del data[agent_id]
        self._save(data)
        return True

    def list_all(self) -> list[QuarantineEntry]:
        return [
            QuarantineEntry(agent_id=k, reason=v["reason"], at=v["at"])
            for k, v in sorted(self._load().items())
        ]


def should_quarantine(
    score: float, threshold: float = DEFAULT_QUARANTINE_THRESHOLD
) -> bool:
    """Pure-function policy: reputation at-or-below threshold → quarantine."""
    return score <= threshold
