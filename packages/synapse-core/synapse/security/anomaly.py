# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Anomaly detection — rate-based outlier alerting per sender.

The detector tracks per-agent message rates inside a fixed-size sliding
window (default 1 minute, 60 1-second buckets). When the most recent
bucket exceeds the per-agent rolling mean by ``z_threshold`` standard
deviations, the message is flagged as anomalous.

This is not an ML model. It is the simplest statistical anomaly check
that catches the obvious cases: an agent that normally sends 1 msg/min
and suddenly bursts to 60 msg/sec gets flagged. A receiver can route a
flagged message into a quarantine review queue without taking a heavy
detection dependency.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field

#: Sliding window in seconds. Each second has its own bucket.
DEFAULT_WINDOW_SECONDS = 60

#: Standard deviations above the rolling mean before we flag an anomaly.
DEFAULT_Z_THRESHOLD = 3.0


@dataclass(frozen=True)
class AnomalyResult:
    """Outcome of :meth:`RateAnomalyDetector.observe`."""

    is_anomaly: bool
    rate_per_second: float
    rolling_mean: float
    rolling_stddev: float
    z_score: float


@dataclass
class _AgentWindow:
    """Per-agent message-count window. One entry per second."""

    window_seconds: int
    buckets: deque[tuple[int, int]] = field(default_factory=deque)

    def _trim(self, now: int) -> None:
        """Drop buckets older than ``window_seconds`` ago."""
        threshold = now - self.window_seconds
        while self.buckets and self.buckets[0][0] <= threshold:
            self.buckets.popleft()

    def record(self, now: int) -> None:
        self._trim(now)
        if self.buckets and self.buckets[-1][0] == now:
            ts, count = self.buckets.pop()
            self.buckets.append((ts, count + 1))
        else:
            self.buckets.append((now, 1))

    def counts(self, now: int) -> list[int]:
        """Return the per-second counts inside the current window."""
        self._trim(now)
        return [count for _ts, count in self.buckets]


class RateAnomalyDetector:
    """Per-agent rate anomaly detector.

    Call :meth:`observe` for each accepted message; it returns an
    :class:`AnomalyResult` indicating whether this message's per-second
    arrival rate is anomalous given the agent's recent history.
    """

    def __init__(
        self,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        z_threshold: float = DEFAULT_Z_THRESHOLD,
    ) -> None:
        if window_seconds <= 1:
            raise ValueError("window_seconds must be > 1")
        if z_threshold <= 0:
            raise ValueError("z_threshold must be > 0")
        self._window_seconds = window_seconds
        self._z_threshold = z_threshold
        self._agents: dict[str, _AgentWindow] = {}

    def observe(
        self, agent_id: str, now: float | None = None
    ) -> AnomalyResult:
        """Record one message from ``agent_id`` and return the anomaly verdict."""
        ts = int(time.time() if now is None else now)
        window = self._agents.setdefault(
            agent_id, _AgentWindow(window_seconds=self._window_seconds)
        )
        window.record(ts)
        counts = window.counts(ts)

        # Need at least two prior data points to compute stddev meaningfully.
        if len(counts) < 3:
            return AnomalyResult(
                is_anomaly=False,
                rate_per_second=float(counts[-1]),
                rolling_mean=0.0,
                rolling_stddev=0.0,
                z_score=0.0,
            )

        current = counts[-1]
        history = counts[:-1]
        mean = sum(history) / len(history)
        variance = sum((c - mean) ** 2 for c in history) / len(history)
        stddev = math.sqrt(variance)

        if stddev == 0:
            # All prior buckets identical → any non-equal current is anomalous.
            is_anomaly = current > mean
            z = float("inf") if is_anomaly else 0.0
        else:
            z = (current - mean) / stddev
            is_anomaly = z >= self._z_threshold

        return AnomalyResult(
            is_anomaly=is_anomaly,
            rate_per_second=float(current),
            rolling_mean=mean,
            rolling_stddev=stddev,
            z_score=z,
        )
