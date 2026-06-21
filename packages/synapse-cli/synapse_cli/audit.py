# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Append-only JSONL audit log."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditEntry:
    action: str
    sender: str
    receiver: str
    task_id: str
    timestamp: str
    signature_hash: str = ""
    approval: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLog:
    """Append-only JSONL audit log."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: AuditEntry) -> None:
        with self._path.open("a") as f:
            f.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")

    def read_all(self) -> list[AuditEntry]:
        if not self._path.exists():
            return []
        entries: list[AuditEntry] = []
        with self._path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(AuditEntry(**data))
                except (json.JSONDecodeError, TypeError):
                    # Skip partial / corrupted lines (interrupted writes).
                    continue
        return entries


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
