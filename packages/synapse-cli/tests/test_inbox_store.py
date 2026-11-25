# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""InboxStore durability + concurrency (known limitation M-1).

The inbox must use WAL journaling and a busy timeout, exactly like the outbox,
so concurrent writers never fail with ``database is locked``.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from synapse_cli.inbox_store import DuplicateTaskError, InboxStore


@pytest.fixture()
def store(tmp_path: Path) -> InboxStore:
    return InboxStore(tmp_path / "inbox.db")


def _insert(store: InboxStore, task_id: str):
    return store.insert(
        task_id=task_id,
        sender="alice",
        task_dict={"id": task_id, "text": "ping"},
        signature="sig-" + task_id,
        sender_score=0.9,
    )


def test_journal_mode_is_wal(store: InboxStore) -> None:
    conn = store._conn()
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() == "wal"


def test_busy_timeout_is_10_seconds(store: InboxStore) -> None:
    conn = store._conn()
    try:
        timeout_ms = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        conn.close()
    assert timeout_ms == 10_000


def test_insert_get_round_trip(store: InboxStore) -> None:
    inserted = _insert(store, "task-1")
    fetched = store.get("task-1")
    assert fetched is not None
    assert fetched == inserted
    assert fetched.sender == "alice"
    assert fetched.status == "pending"
    assert fetched.sender_score == pytest.approx(0.9)
    assert store.get("missing") is None


def test_duplicate_insert_raises_duplicate_task_error(store: InboxStore) -> None:
    _insert(store, "task-dup")
    with pytest.raises(DuplicateTaskError):
        _insert(store, "task-dup")
    assert len(store.list_all()) == 1


def test_concurrent_inserts_from_two_threads_all_land(tmp_path: Path) -> None:
    store = InboxStore(tmp_path / "concurrent.db")
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def worker(prefix: str) -> None:
        try:
            barrier.wait()
            for i in range(50):
                _insert(store, f"{prefix}-{i}")
        except BaseException as exc:  # noqa: BLE001 - surface any failure
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("a",)),
        threading.Thread(target=worker, args=("b",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert errors == [], f"concurrent insert failed: {errors!r}"
    ids = {row.task_id for row in store.list_all()}
    assert len(ids) == 100
