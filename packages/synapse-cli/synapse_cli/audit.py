# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Append-only, hash-chained JSONL audit log.

Every entry includes ``prev_hash`` (the SHA-256 of the previous entry's
content + its own previous hash) and ``entry_hash`` (the SHA-256 of this
entry's content + its ``prev_hash``). A genesis entry uses ``prev_hash =
"0" * 64``.

Tampering with any past entry — modifying it, deleting it, or inserting a
forged one — invalidates the chain at the next ``verify_chain`` walk. This
is the "forensically ready" property: the audit log is detectably immutable
without trusting filesystem ACLs alone.

Backwards compatible: older entries written before the chain was introduced
still parse with empty ``prev_hash`` / ``entry_hash``. ``verify_chain``
reports those as ``"unchained"`` rather than a tamper failure so an operator
can distinguish "old log" from "tampered log".
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

#: The hash used to seed the chain. Any 32-byte all-zero value works.
GENESIS_PREV_HASH = "0" * 64


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
    prev_hash: str = ""
    entry_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of :meth:`AuditLog.verify_chain`."""

    ok: bool
    total_entries: int
    chained_entries: int
    unchained_entries: int
    tampered_at_index: int = -1
    reason: str = ""


def _content_digest(entry: AuditEntry, prev_hash: str) -> str:
    """Compute the SHA-256 of ``entry``'s content + ``prev_hash``.

    The hashed bytes are the canonical JSON of every field **except**
    ``entry_hash`` itself. Including ``prev_hash`` in the digest is what
    binds each entry to all preceding ones.
    """
    payload = {**entry.to_dict(), "prev_hash": prev_hash}
    payload.pop("entry_hash", None)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class AuditLog:
    """Append-only, hash-chained JSONL audit log.

    The log file is plain JSONL — one entry per line. The chain is internal
    to each entry (``prev_hash`` + ``entry_hash``), not the file structure,
    so the log remains human-readable and grep-able.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash: str | None = None

    def _read_last_hash(self) -> str:
        """Return the ``entry_hash`` of the last entry, or genesis if empty."""
        if self._last_hash is not None:
            return self._last_hash
        if not self._path.exists():
            self._last_hash = GENESIS_PREV_HASH
            return self._last_hash
        last = GENESIS_PREV_HASH
        with self._path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("entry_hash"):
                    last = str(data["entry_hash"])
        self._last_hash = last
        return last

    def append(self, entry: AuditEntry) -> AuditEntry:
        """Append ``entry``, returning the fully-chained version actually written.

        The caller's ``entry`` may have empty ``prev_hash`` / ``entry_hash`` —
        we compute and fill them. The returned :class:`AuditEntry` has the
        committed hash values.
        """
        prev = self._read_last_hash()
        digest = _content_digest(entry, prev)
        chained = AuditEntry(
            action=entry.action,
            sender=entry.sender,
            receiver=entry.receiver,
            task_id=entry.task_id,
            timestamp=entry.timestamp,
            signature_hash=entry.signature_hash,
            approval=entry.approval,
            detail=entry.detail,
            prev_hash=prev,
            entry_hash=digest,
        )
        with self._path.open("a") as f:
            f.write(json.dumps(chained.to_dict(), sort_keys=True) + "\n")
        self._last_hash = digest
        return chained

    def read_all(self) -> list[AuditEntry]:
        """Return every entry in file order. Skips unparseable partial lines."""
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

    def verify_chain(self) -> VerifyResult:
        """Walk the log and verify the hash chain end-to-end.

        Returns ``ok=True`` iff every entry that carries a chain
        (``prev_hash`` + ``entry_hash`` both set) chains correctly to the
        previous one. Pre-chain legacy entries are tolerated and counted as
        ``unchained_entries`` — they don't fail the verification.
        """
        entries = self.read_all()
        prev = GENESIS_PREV_HASH
        chained = 0
        unchained = 0
        for i, entry in enumerate(entries):
            if not entry.entry_hash:
                unchained += 1
                continue
            if entry.prev_hash != prev:
                return VerifyResult(
                    ok=False,
                    total_entries=len(entries),
                    chained_entries=chained,
                    unchained_entries=unchained,
                    tampered_at_index=i,
                    reason=(
                        f"prev_hash mismatch at index {i}: "
                        f"expected {prev[:16]}…, got {entry.prev_hash[:16]}…"
                    ),
                )
            expected = _content_digest(entry, prev)
            if entry.entry_hash != expected:
                return VerifyResult(
                    ok=False,
                    total_entries=len(entries),
                    chained_entries=chained,
                    unchained_entries=unchained,
                    tampered_at_index=i,
                    reason=(
                        f"entry_hash mismatch at index {i}: "
                        f"content does not match recorded digest"
                    ),
                )
            prev = entry.entry_hash
            chained += 1
        return VerifyResult(
            ok=True,
            total_entries=len(entries),
            chained_entries=chained,
            unchained_entries=unchained,
            reason="chain intact",
        )


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
