# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Durable outbox — survives crashes, target offline, and process restart.

A sender enqueues a pre-built A2A JSON-RPC envelope (already signed) and a
target endpoint URL. The :class:`outbox_worker.OutboxWorker` drains the queue
in the background with exponential backoff. After ``MAX_ATTEMPTS`` failures a
row moves to the ``dead`` state — it is never silently dropped.

The schema is deliberately small. The outbox stores **what to send** and the
**delivery state**. It does not store the agent's task semantics — that lives
in the inbox on the receiving side and the audit log on the sending side.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

#: Maximum retry attempts before a row moves to ``dead``.
MAX_ATTEMPTS = 6

#: Exponential backoff schedule (seconds). Index = attempt number.
#: 5s, 30s, 3m, 15m, 1h, 6h. After attempt 6 the row is marked dead.
BACKOFF_SECONDS: tuple[int, ...] = (5, 30, 180, 900, 3600, 21600)


@dataclass(frozen=True)
class OutboxRow:
    task_id: str
    target_id: str
    endpoint_url: str
    sender_id: str
    payload: bytes
    signature_hex: str
    sign_timestamp: int
    state: str  # queued | sent | failed | dead
    attempts: int
    next_retry_at: float
    enqueued_at: str
    last_error: str = ""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def backoff_for(attempt: int) -> int:
    """Return the backoff (seconds) for the *next* try after ``attempt`` failures."""
    if attempt < 0:
        return BACKOFF_SECONDS[0]
    if attempt >= len(BACKOFF_SECONDS):
        return BACKOFF_SECONDS[-1]
    return BACKOFF_SECONDS[attempt]


class OutboxStore:
    """SQLite-backed durable send queue. Safe for one writer + many readers."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    task_id        TEXT PRIMARY KEY,
                    target_id      TEXT NOT NULL,
                    endpoint_url   TEXT NOT NULL,
                    sender_id      TEXT NOT NULL,
                    payload        BLOB NOT NULL,
                    signature_hex  TEXT NOT NULL,
                    sign_timestamp INTEGER NOT NULL,
                    state          TEXT NOT NULL,
                    attempts       INTEGER NOT NULL DEFAULT 0,
                    next_retry_at  REAL NOT NULL,
                    enqueued_at    TEXT NOT NULL,
                    last_error     TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS outbox_state_retry "
                "ON outbox(state, next_retry_at)"
            )

    def enqueue(
        self,
        task_id: str,
        target_id: str,
        endpoint_url: str,
        sender_id: str,
        payload: bytes,
        signature_hex: str,
        sign_timestamp: int,
    ) -> OutboxRow:
        row = OutboxRow(
            task_id=task_id,
            target_id=target_id,
            endpoint_url=endpoint_url,
            sender_id=sender_id,
            payload=payload,
            signature_hex=signature_hex,
            sign_timestamp=sign_timestamp,
            state="queued",
            attempts=0,
            next_retry_at=time.time(),
            enqueued_at=now_iso(),
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO outbox VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.task_id,
                    row.target_id,
                    row.endpoint_url,
                    row.sender_id,
                    row.payload,
                    row.signature_hex,
                    row.sign_timestamp,
                    row.state,
                    row.attempts,
                    row.next_retry_at,
                    row.enqueued_at,
                    row.last_error,
                ),
            )
        return row

    def claim_due(self, now: float | None = None, limit: int = 16) -> list[OutboxRow]:
        """Return rows in state=queued|failed whose next_retry_at has passed."""
        threshold = time.time() if now is None else now
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM outbox "
                "WHERE state IN ('queued','failed') AND next_retry_at <= ? "
                "ORDER BY next_retry_at ASC LIMIT ?",
                (threshold, limit),
            )
            return [self._row(r) for r in cur.fetchall()]

    def mark_sent(self, task_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE outbox SET state='sent', last_error='', "
                "next_retry_at=0 WHERE task_id=?",
                (task_id,),
            )

    def mark_failed(
        self, task_id: str, attempt: int, error: str
    ) -> tuple[str, float]:
        """Mark a row failed. Returns (new_state, next_retry_at)."""
        if attempt + 1 >= MAX_ATTEMPTS:
            new_state = "dead"
            next_at = 0.0
        else:
            new_state = "failed"
            next_at = time.time() + backoff_for(attempt)
        with self._conn() as conn:
            conn.execute(
                "UPDATE outbox SET state=?, attempts=?, next_retry_at=?, "
                "last_error=? WHERE task_id=?",
                (new_state, attempt + 1, next_at, error[:500], task_id),
            )
        return new_state, next_at

    def requeue(self, task_id: str) -> bool:
        """Reset a dead row to queued for immediate retry. Returns True if updated."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE outbox SET state='queued', attempts=0, "
                "next_retry_at=?, last_error='' "
                "WHERE task_id=? AND state IN ('dead','failed')",
                (time.time(), task_id),
            )
            return cur.rowcount > 0

    def get(self, task_id: str) -> OutboxRow | None:
        with self._conn() as conn:
            cur = conn.execute("SELECT * FROM outbox WHERE task_id=?", (task_id,))
            r = cur.fetchone()
        return self._row(r) if r else None

    def list_by_state(self, states: Iterable[str]) -> list[OutboxRow]:
        states = list(states)
        if not states:
            return []
        placeholders = ",".join("?" * len(states))
        with self._conn() as conn:
            cur = conn.execute(
                f"SELECT * FROM outbox WHERE state IN ({placeholders}) "
                "ORDER BY enqueued_at ASC",
                states,
            )
            return [self._row(r) for r in cur.fetchall()]

    def purge_sent(self, older_than_seconds: int = 86400) -> int:
        """Delete rows in state=sent that finished more than N seconds ago."""
        with self._conn() as conn:
            cutoff_iso = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(time.time() - older_than_seconds),
            )
            cur = conn.execute(
                "DELETE FROM outbox WHERE state='sent' AND enqueued_at < ?",
                (cutoff_iso,),
            )
            return cur.rowcount

    @staticmethod
    def _row(r: tuple) -> OutboxRow:
        return OutboxRow(
            task_id=r[0],
            target_id=r[1],
            endpoint_url=r[2],
            sender_id=r[3],
            payload=r[4],
            signature_hex=r[5],
            sign_timestamp=r[6],
            state=r[7],
            attempts=r[8],
            next_retry_at=r[9],
            enqueued_at=r[10],
            last_error=r[11],
        )
