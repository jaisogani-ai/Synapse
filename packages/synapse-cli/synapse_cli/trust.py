# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Trust/reputation lookup — reuses Phase B capability model.

Persistent JSON store keyed by agent_id. Reputation score in [0.0, 1.0].
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

#: Default minimum reputation to send-task without explicit --confirm.
DEFAULT_TRUST_THRESHOLD = 0.5


@dataclass(frozen=True)
class TrustRecord:
    agent_id: str
    score: float
    domain: str = "default"


class TrustStore:
    """Persistent JSON-backed trust store."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._scores: dict[str, float] = {}
        if path is not None and path.exists():
            self._load()

    def _load(self) -> None:
        assert self._path is not None
        with self._path.open() as f:
            self._scores = dict(json.load(f))

    def _persist(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w") as f:
            json.dump(self._scores, f, indent=2, sort_keys=True)

    def set_score(self, agent_id: str, score: float) -> None:
        if not 0.0 <= score <= 1.0:
            raise ValueError("score must be in [0.0, 1.0]")
        self._scores = {**self._scores, agent_id: score}
        self._persist()

    def get_score(self, agent_id: str, default: float = 0.5) -> float:
        return self._scores.get(agent_id, default)

    def get_record(self, agent_id: str) -> TrustRecord:
        return TrustRecord(agent_id=agent_id, score=self.get_score(agent_id))

    def is_trusted(
        self, agent_id: str, threshold: float = DEFAULT_TRUST_THRESHOLD
    ) -> bool:
        return self.get_score(agent_id) >= threshold
