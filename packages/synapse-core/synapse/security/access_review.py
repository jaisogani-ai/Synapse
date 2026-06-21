# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Access review — summarize the audit log by sender / action / time range.

This is the "Access Review" surface of the v0.1.0-alpha trust layer. An
operator runs ``synapse audit review`` (wired through `__main__`) and gets
a structured summary of who did what, when, and how often — derived
directly from the append-only hash-chained audit log.

There is no separate database. The audit log *is* the source of truth.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class AgentActivity:
    """Per-agent activity summary inside the review window."""

    agent_id: str
    total: int
    actions: dict[str, int]


@dataclass(frozen=True)
class AccessReport:
    """Result of :func:`review`."""

    window_from: str  # ISO-8601 lower bound (inclusive)
    window_to: str    # ISO-8601 upper bound (inclusive)
    total_entries: int
    by_action: dict[str, int]
    by_sender: tuple[AgentActivity, ...]
    by_receiver: tuple[AgentActivity, ...]


def _in_window(timestamp: str, lo: str, hi: str) -> bool:
    """ISO-8601 strings sort lexically, so direct compares are correct."""
    return lo <= timestamp <= hi


def review(
    entries: Iterable["object"],  # AuditEntry, kept loose to avoid the import cycle
    *,
    window_from: str = "",
    window_to: str = "9999-12-31T23:59:59Z",
) -> AccessReport:
    """Summarize an audit-log slice into a flat :class:`AccessReport`."""
    by_action: Counter[str] = Counter()
    sender_total: Counter[str] = Counter()
    sender_actions: dict[str, Counter[str]] = {}
    receiver_total: Counter[str] = Counter()
    receiver_actions: dict[str, Counter[str]] = {}
    total = 0

    for entry in entries:
        ts = getattr(entry, "timestamp", "")
        if window_from and not _in_window(ts, window_from, window_to):
            continue
        action = getattr(entry, "action", "")
        sender = getattr(entry, "sender", "")
        receiver = getattr(entry, "receiver", "")
        total += 1
        by_action[action] += 1
        if sender:
            sender_total[sender] += 1
            sender_actions.setdefault(sender, Counter())[action] += 1
        if receiver:
            receiver_total[receiver] += 1
            receiver_actions.setdefault(receiver, Counter())[action] += 1

    def _activity(
        total_counter: Counter[str], action_map: dict[str, Counter[str]]
    ) -> tuple[AgentActivity, ...]:
        return tuple(
            AgentActivity(
                agent_id=agent_id,
                total=total_counter[agent_id],
                actions=dict(action_map.get(agent_id, Counter())),
            )
            for agent_id, _ in total_counter.most_common()
        )

    return AccessReport(
        window_from=window_from,
        window_to=window_to,
        total_entries=total,
        by_action=dict(by_action),
        by_sender=_activity(sender_total, sender_actions),
        by_receiver=_activity(receiver_total, receiver_actions),
    )
