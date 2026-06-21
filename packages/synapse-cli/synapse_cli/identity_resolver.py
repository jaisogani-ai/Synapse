# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Resolve an agent id to its endpoint via the daemon identity store.

JSON-backed identity registry mapping agent_id → endpoint URL. In production
the daemon owns this; for CLI testing each daemon instance has its own JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentEndpoint:
    agent_id: str
    url: str


class IdentityResolver:
    """Resolve agent_id → A2A endpoint URL."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._registry: dict[str, str] = {}
        if path.exists():
            self._load()

    def _load(self) -> None:
        with self._path.open() as f:
            self._registry = dict(json.load(f))

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w") as f:
            json.dump(self._registry, f, indent=2, sort_keys=True)

    def register(self, agent_id: str, url: str) -> None:
        self._registry = {**self._registry, agent_id: url}
        self._persist()

    def resolve(self, agent_id: str) -> AgentEndpoint | None:
        url = self._registry.get(agent_id)
        if url is None:
            return None
        return AgentEndpoint(agent_id=agent_id, url=url)
