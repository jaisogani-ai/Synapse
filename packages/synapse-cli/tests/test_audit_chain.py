# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Hash-chained audit log — tamper detection.

These tests cover the v0.1.0-alpha "forensically ready" property: an
append-only JSONL log where each entry binds to all preceding ones via
SHA-256, so any retroactive edit or deletion is detectable.
"""

from __future__ import annotations

import json
from pathlib import Path


from synapse_cli.audit import (
    GENESIS_PREV_HASH,
    AuditEntry,
    AuditLog,
    VerifyResult,
    now_iso,
)


def _entry(action: str = "send_task", task_id: str = "t1") -> AuditEntry:
    return AuditEntry(
        action=action,
        sender="alice",
        receiver="bob",
        task_id=task_id,
        timestamp=now_iso(),
        approval="auto",
        detail="ok",
    )


def test_genesis_entry_chains_to_zero_prev_hash(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    chained = log.append(_entry())
    assert chained.prev_hash == GENESIS_PREV_HASH
    assert len(chained.entry_hash) == 64


def test_each_entry_chains_to_previous(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    first = log.append(_entry(task_id="t1"))
    second = log.append(_entry(task_id="t2"))
    third = log.append(_entry(task_id="t3"))
    assert second.prev_hash == first.entry_hash
    assert third.prev_hash == second.entry_hash


def test_verify_clean_chain_returns_ok(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    for i in range(5):
        log.append(_entry(task_id=f"t{i}"))
    result = log.verify_chain()
    assert isinstance(result, VerifyResult)
    assert result.ok
    assert result.total_entries == 5
    assert result.chained_entries == 5
    assert result.unchained_entries == 0
    assert result.tampered_at_index == -1


def test_verify_detects_modified_entry_content(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    for i in range(3):
        log.append(_entry(task_id=f"t{i}"))

    # Read the file, modify the middle entry's `detail`, write back.
    lines = path.read_text().splitlines()
    middle = json.loads(lines[1])
    middle["detail"] = "TAMPERED"
    lines[1] = json.dumps(middle, sort_keys=True)
    path.write_text("\n".join(lines) + "\n")

    result = log.verify_chain()
    assert not result.ok
    assert result.tampered_at_index == 1
    assert "entry_hash mismatch" in result.reason


def test_verify_detects_deleted_entry(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    for i in range(4):
        log.append(_entry(task_id=f"t{i}"))

    # Delete the second entry. Subsequent entries' prev_hash no longer matches.
    lines = path.read_text().splitlines()
    del lines[1]
    path.write_text("\n".join(lines) + "\n")

    result = log.verify_chain()
    assert not result.ok
    # The entry that's now at index 1 should fail because its prev_hash
    # still points at the deleted entry's hash, not the entry actually at
    # index 0 in the surviving file.
    assert result.tampered_at_index == 1
    assert "prev_hash mismatch" in result.reason


def test_verify_detects_inserted_forged_entry(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.append(_entry(task_id="t1"))
    log.append(_entry(task_id="t2"))

    # Forge an entry with a plausible but invented entry_hash and insert it.
    lines = path.read_text().splitlines()
    forged = json.dumps(
        {
            "action": "forged",
            "sender": "evil",
            "receiver": "bob",
            "task_id": "FORGED",
            "timestamp": now_iso(),
            "signature_hash": "",
            "approval": "",
            "detail": "",
            "prev_hash": "f" * 64,
            "entry_hash": "e" * 64,
        },
        sort_keys=True,
    )
    lines.insert(1, forged)
    path.write_text("\n".join(lines) + "\n")

    result = log.verify_chain()
    assert not result.ok
    assert result.tampered_at_index == 1


def test_unchained_legacy_entries_do_not_fail_verification(tmp_path: Path) -> None:
    """Old logs from before the chain feature should verify as 'ok with unchained'."""
    path = tmp_path / "audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write three entries by hand without prev_hash / entry_hash.
    for i in range(3):
        legacy = json.dumps(
            {
                "action": "send_task",
                "sender": "alice",
                "receiver": "bob",
                "task_id": f"t{i}",
                "timestamp": now_iso(),
                "signature_hash": "",
                "approval": "",
                "detail": "",
                "prev_hash": "",
                "entry_hash": "",
            },
            sort_keys=True,
        )
        with path.open("a") as f:
            f.write(legacy + "\n")

    log = AuditLog(path)
    result = log.verify_chain()
    assert result.ok
    assert result.chained_entries == 0
    assert result.unchained_entries == 3


def test_mixed_legacy_then_chained_continues_chain_from_genesis(tmp_path: Path) -> None:
    """If new entries are appended to a legacy log, the chain starts from genesis."""
    path = tmp_path / "audit.jsonl"
    # Legacy entry first
    with path.open("a") as f:
        legacy = json.dumps(
            {
                "action": "old",
                "sender": "x",
                "receiver": "y",
                "task_id": "old",
                "timestamp": now_iso(),
                "signature_hash": "",
                "approval": "",
                "detail": "",
                "prev_hash": "",
                "entry_hash": "",
            },
            sort_keys=True,
        )
        f.write(legacy + "\n")

    # Now append two chained entries. The first chained entry's prev_hash
    # is the genesis (because there is no prior entry_hash to read).
    log = AuditLog(path)
    a = log.append(_entry(task_id="new1"))
    b = log.append(_entry(task_id="new2"))
    assert a.prev_hash == GENESIS_PREV_HASH
    assert b.prev_hash == a.entry_hash

    result = log.verify_chain()
    assert result.ok
    assert result.unchained_entries == 1
    assert result.chained_entries == 2
