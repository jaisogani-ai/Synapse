# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""SQLite-backed pending-tasks table for the receiving daemon.

This is a *task queue*, not a memory tier. It stores received A2A tasks until
the user explicitly accepts or rejects them.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DuplicateTaskError(Exception):
    """Raised when an INSERT would violate the task_id PRIMARY KEY (replay)."""


@dataclass(frozen=True)
class InboxRow:
    task_id: str
    sender: str
    status: str  # pending | accepted | rejected | completed
    task_json: str
    signature: str
    received_at: str
    sender_score: float
    result_json: str = ""


class InboxStore:
    """Minimal SQLite store for incoming A2A tasks."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inbox (
                    task_id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    status TEXT NOT NULL,
                    task_json TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    sender_score REAL NOT NULL,
                    result_json TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def insert(
        self,
        task_id: str,
        sender: str,
        task_dict: dict[str, Any],
        signature: str,
        sender_score: float,
    ) -> InboxRow:
        row = InboxRow(
            task_id=task_id,
            sender=sender,
            status="pending",
            task_json=json.dumps(task_dict, sort_keys=True),
            signature=signature,
            received_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            sender_score=sender_score,
        )
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO inbox VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row.task_id,
                        row.sender,
                        row.status,
                        row.task_json,
                        row.signature,
                        row.received_at,
                        row.sender_score,
                        row.result_json,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateTaskError(
                f"task_id already received (replay?): {task_id}"
            ) from exc
        return row

    def get(self, task_id: str) -> InboxRow | None:
        with self._conn() as conn:
            cur = conn.execute("SELECT * FROM inbox WHERE task_id = ?", (task_id,))
            r = cur.fetchone()
        if r is None:
            return None
        return InboxRow(*r)

    def update_status(
        self, task_id: str, status: str, result_json: str = ""
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE inbox SET status = ?, result_json = ? WHERE task_id = ?",
                (status, result_json, task_id),
            )

    def list_all(self) -> list[InboxRow]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM inbox ORDER BY received_at ASC"
            )
            return [InboxRow(*r) for r in cur.fetchall()]
