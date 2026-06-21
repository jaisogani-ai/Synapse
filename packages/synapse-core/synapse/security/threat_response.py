# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Threat response — auto-block agents that repeatedly fail Gate 1.

The receiver counts consecutive Gate-1 failures (bad signature, missing
timestamp, unsigned envelope) per agent. After ``MAX_CONSECUTIVE_FAILURES``
the agent is auto-quarantined: an entry is added to the
:class:`quarantine.QuarantineStore` so all further messages are rejected
until an operator releases it.

Successful messages reset the counter. The whole thing is in-memory per
process — restart clears it. That is deliberate: a process restart is a
clean slate, and the counter is a defence against active attack, not a
forensic record (the audit log carries that).
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Number of consecutive Gate-1 failures before auto-quarantine fires.
MAX_CONSECUTIVE_FAILURES = 5


@dataclass
class FailureTracker:
    """Per-agent consecutive Gate-1 failure counter.

    A bounded dict; if you have ten million unique senders sending one
    failure each, this grows to ten million entries. For v0.1.0-alpha the
    expected sender population is tens or hundreds (your devices + a few
    peers), so this is fine.
    """

    max_consecutive: int = MAX_CONSECUTIVE_FAILURES
    _counts: dict[str, int] = field(default_factory=dict)

    def record_failure(self, agent_id: str) -> int:
        """Return the new consecutive-failure count after this failure."""
        count = self._counts.get(agent_id, 0) + 1
        self._counts[agent_id] = count
        return count

    def record_success(self, agent_id: str) -> None:
        """Reset the counter for ``agent_id`` after a clean message."""
        self._counts.pop(agent_id, None)

    def should_block(self, agent_id: str) -> bool:
        """Whether this agent has hit the auto-block threshold."""
        return self._counts.get(agent_id, 0) >= self.max_consecutive

    def count_for(self, agent_id: str) -> int:
        return self._counts.get(agent_id, 0)
