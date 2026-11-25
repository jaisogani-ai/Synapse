# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Durable outbox lifecycle: offline -> queue -> retry -> dead -> requeue.

Drives :class:`OutboxWorker.tick` directly with a stub ``deliver`` function so
no network or background thread is needed.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from synapse_cli.audit import AuditLog
from synapse_cli.outbox_store import (
    BACKOFF_SECONDS,
    MAX_ATTEMPTS,
    OutboxStore,
    backoff_for,
)
from synapse_cli.outbox_worker import OutboxWorker
from synapse_cli.transport import TransportUnreachable

TASK_ID = "task-outbox-1"


class _Target:
    """A fake remote peer that can be switched online/offline."""

    def __init__(self) -> None:
        self.online = False
        self.calls = 0

    def deliver(self, url, payload, sender_id, signature_hex, timestamp, token):
        self.calls += 1
        if not self.online:
            raise TransportUnreachable(f"{url} is offline")
        return {"jsonrpc": "2.0", "result": {"taskId": TASK_ID}}


@pytest.fixture()
def env(tmp_path: Path):
    store = OutboxStore(tmp_path / "outbox.db")
    audit = AuditLog(tmp_path / "audit.jsonl")
    target = _Target()
    worker = OutboxWorker(store=store, audit=audit, deliver=target.deliver)
    store.enqueue(
        task_id=TASK_ID,
        target_id="bob",
        endpoint_url="http://127.0.0.1:9/a2a",
        sender_id="alice",
        payload=b'{"jsonrpc":"2.0","method":"message/send"}',
        signature_hex="ab" * 32,
        sign_timestamp=int(time.time()),
    )
    return {"store": store, "audit": audit, "target": target, "worker": worker}


def _force_due(store: OutboxStore, task_id: str) -> None:
    """Skip the backoff wait so the next tick retries immediately."""
    with store._conn() as conn:
        conn.execute(
            "UPDATE outbox SET next_retry_at=0 WHERE task_id=?", (task_id,)
        )


def _actions(audit: AuditLog) -> list[str]:
    return [e.action for e in audit.read_all()]


def test_offline_target_queues_then_retries_to_dead_then_requeue_delivers(env) -> None:
    store, target, worker = env["store"], env["target"], env["worker"]

    # Freshly enqueued row is queued and immediately due.
    row = store.get(TASK_ID)
    assert row is not None and row.state == "queued" and row.attempts == 0

    # First attempt fails: row moves to `failed` with a future retry time.
    assert worker.tick() == 1
    row = store.get(TASK_ID)
    assert row.state == "failed" and row.attempts == 1
    assert row.next_retry_at > time.time()
    assert "offline" in row.last_error

    # Not due yet, so a second tick does nothing.
    assert worker.tick() == 0
    assert target.calls == 1

    # Keep failing until MAX_ATTEMPTS is exhausted -> dead, never dropped.
    for _ in range(MAX_ATTEMPTS - 1):
        _force_due(store, TASK_ID)
        assert worker.tick() == 1
    row = store.get(TASK_ID)
    assert row.state == "dead" and row.attempts == MAX_ATTEMPTS
    assert target.calls == MAX_ATTEMPTS

    # Dead rows are no longer claimed by the worker.
    _force_due(store, TASK_ID)
    assert worker.tick() == 0
    assert [r.task_id for r in store.list_by_state(["dead"])] == [TASK_ID]

    # Operator requeues; target comes back online; delivery succeeds.
    assert store.requeue(TASK_ID) is True
    row = store.get(TASK_ID)
    assert row.state == "queued" and row.attempts == 0 and row.last_error == ""
    target.online = True
    assert worker.tick() == 1
    assert store.get(TASK_ID).state == "sent"

    # Audit trail records every step.
    actions = _actions(env["audit"])
    assert actions.count("outbox_retry") == MAX_ATTEMPTS - 1
    assert actions.count("outbox_dead") == 1
    assert actions.count("outbox_delivered") == 1


def test_transient_failure_recovers_without_going_dead(env) -> None:
    store, target, worker = env["store"], env["target"], env["worker"]
    worker.tick()  # offline -> failed
    assert store.get(TASK_ID).state == "failed"

    target.online = True
    _force_due(store, TASK_ID)
    assert worker.tick() == 1
    row = store.get(TASK_ID)
    assert row.state == "sent"
    assert row.last_error == ""
    assert "outbox_dead" not in _actions(env["audit"])


def test_requeue_only_applies_to_dead_or_failed_rows(env) -> None:
    store, target, worker = env["store"], env["target"], env["worker"]
    # queued row: nothing to requeue.
    assert store.requeue(TASK_ID) is False
    target.online = True
    worker.tick()
    assert store.get(TASK_ID).state == "sent"
    # sent row: must not be resurrected.
    assert store.requeue(TASK_ID) is False
    assert store.requeue("no-such-task") is False


def test_backoff_schedule() -> None:
    assert BACKOFF_SECONDS == (5, 30, 180, 900, 3600, 21600)
    assert backoff_for(-1) == 5
    assert [backoff_for(i) for i in range(6)] == list(BACKOFF_SECONDS)
    assert backoff_for(99) == 21600


def test_queued_row_survives_store_reopen(tmp_path: Path) -> None:
    path = tmp_path / "outbox.db"
    first = OutboxStore(path)
    first.enqueue(
        task_id="durable-1",
        target_id="bob",
        endpoint_url="http://127.0.0.1:9/a2a",
        sender_id="alice",
        payload=b"payload-bytes",
        signature_hex="cd" * 32,
        sign_timestamp=123,
    )
    del first

    reopened = OutboxStore(path)
    row = reopened.get("durable-1")
    assert row is not None
    assert row.state == "queued"
    assert row.payload == b"payload-bytes"
    assert [r.task_id for r in reopened.claim_due()] == ["durable-1"]
