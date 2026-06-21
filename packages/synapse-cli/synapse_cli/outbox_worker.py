# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Background worker that drains the durable outbox.

The worker is a single Python thread that polls :class:`OutboxStore.claim_due`
and calls :func:`transport.post_jsonrpc` for each due row. On success the row
moves to ``sent``. On failure the row is rescheduled with exponential backoff
or moved to ``dead`` after ``MAX_ATTEMPTS``.

One worker per sender daemon is enough. The store uses SQLite WAL so the CLI
can read outbox state while the worker is running.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from synapse.security.capabilities import DEFAULT_A2A_CAPABILITIES
from synapse.security.zero_trust import ZeroTrustNetwork

from .audit import AuditEntry, AuditLog, now_iso
from .outbox_store import OutboxRow, OutboxStore
from .transport import TransportUnreachable, post_jsonrpc

#: How long the worker sleeps between empty polls.
DEFAULT_POLL_SECONDS = 1.0

#: Signature: ``(url, payload, sender_id, signature_hex, timestamp, token) -> dict``.
DeliverFn = Callable[[str, bytes, str, str, int, str], dict]


def _default_deliver(
    url: str,
    payload: bytes,
    sender_id: str,
    signature_hex: str,
    timestamp: int,
    token: str,
) -> dict:
    return post_jsonrpc(
        url, payload, sender_id, signature_hex, timestamp=timestamp, token=token,
    )


@dataclass
class OutboxWorker:
    """Polls the outbox and delivers due rows. Stop with :meth:`stop`.

    The worker re-issues a fresh JWT for each delivery so a row that sits
    in the queue longer than the token TTL still arrives with a valid
    capability assertion. Capability set is :data:`DEFAULT_A2A_CAPABILITIES`.
    """

    store: OutboxStore
    audit: AuditLog
    network: ZeroTrustNetwork | None = None
    capabilities: tuple[str, ...] = field(default=DEFAULT_A2A_CAPABILITIES)
    poll_seconds: float = DEFAULT_POLL_SECONDS
    deliver: DeliverFn = _default_deliver

    def __post_init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def tick(self) -> int:
        """Process every due row right now. Returns the number processed.

        Exposed for tests so we don't have to wait for the polling thread.
        """
        rows = self.store.claim_due()
        for row in rows:
            self._attempt(row)
        return len(rows)

    def _run(self) -> None:
        while not self._stop.is_set():
            processed = self.tick()
            if processed == 0:
                self._stop.wait(timeout=self.poll_seconds)

    def _attempt(self, row: OutboxRow) -> None:
        token = ""
        if self.network is not None and self.network.has_identity(row.sender_id):
            token = self.network.issue_token(
                row.sender_id, capabilities=list(self.capabilities)
            )
        try:
            self.deliver(
                row.endpoint_url,
                row.payload,
                row.sender_id,
                row.signature_hex,
                row.sign_timestamp,
                token,
            )
        except TransportUnreachable as exc:
            new_state, _ = self.store.mark_failed(
                row.task_id, row.attempts, str(exc)
            )
            self.audit.append(
                AuditEntry(
                    action=(
                        "outbox_dead" if new_state == "dead" else "outbox_retry"
                    ),
                    sender=row.sender_id,
                    receiver=row.target_id,
                    task_id=row.task_id,
                    timestamp=now_iso(),
                    detail=f"attempt={row.attempts + 1} error={exc}",
                )
            )
        except Exception as exc:  # noqa: BLE001 — defensive: log + retry
            new_state, _ = self.store.mark_failed(
                row.task_id, row.attempts, str(exc)
            )
            self.audit.append(
                AuditEntry(
                    action=(
                        "outbox_dead" if new_state == "dead" else "outbox_retry"
                    ),
                    sender=row.sender_id,
                    receiver=row.target_id,
                    task_id=row.task_id,
                    timestamp=now_iso(),
                    detail=f"attempt={row.attempts + 1} error={exc!r}",
                )
            )
        else:
            self.store.mark_sent(row.task_id)
            self.audit.append(
                AuditEntry(
                    action="outbox_delivered",
                    sender=row.sender_id,
                    receiver=row.target_id,
                    task_id=row.task_id,
                    timestamp=now_iso(),
                    signature_hash=row.signature_hex[:16],
                )
            )
