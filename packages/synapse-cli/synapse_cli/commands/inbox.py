# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""`synapse inbox` — list / accept / reject received A2A tasks."""

from __future__ import annotations

import json
from dataclasses import dataclass

from synapse.security.capabilities import DEFAULT_A2A_CAPABILITIES

from ..a2a import JsonRpcRequest, METHOD_TASKS_RESULT
from ..a2a_signer import A2ASigner
from ..audit import AuditEntry, AuditLog, now_iso
from ..identity_resolver import IdentityResolver
from ..inbox_store import InboxStore
from ..transport import TransportUnreachable, post_jsonrpc
from ..trust import DEFAULT_TRUST_THRESHOLD


@dataclass(frozen=True)
class InboxSummary:
    task_id: str
    sender: str
    status: str
    received_at: str
    sender_score: float
    preview: str  # redacted if low-rep + still pending


def list_inbox(
    store: InboxStore, threshold: float = DEFAULT_TRUST_THRESHOLD
) -> list[InboxSummary]:
    """List received tasks. Low-rep + pending tasks are redacted until accept."""
    out: list[InboxSummary] = []
    for row in store.list_all():
        if row.sender_score < threshold and row.status == "pending":
            preview = "<redacted: low-reputation sender, run `synapse inbox accept> to view>"
        else:
            try:
                task = json.loads(row.task_json)
                hist = task.get("history") or []
                first_text = ""
                if hist:
                    for part in hist[0].get("parts", []):
                        if part.get("kind") == "text":
                            first_text = part.get("text", "")
                            break
                preview = first_text[:80]
            except json.JSONDecodeError:
                preview = "<invalid task json>"
        out.append(
            InboxSummary(
                task_id=row.task_id,
                sender=row.sender,
                status=row.status,
                received_at=row.received_at,
                sender_score=row.sender_score,
                preview=preview,
            )
        )
    return out


@dataclass(frozen=True)
class ReviewResult:
    """Full, un-redacted view of a received task — for the operator to read
    before calling ``accept`` or ``reject``."""

    ok: bool
    task_id: str
    sender: str
    sender_score: float
    status: str
    received_at: str
    text: str = ""
    attachments: tuple[dict, ...] = ()
    reason: str = ""


def review_task(task_id: str, store: InboxStore) -> ReviewResult:
    """Return the full contents of an inbox row for human review.

    Reveals text and attachment metadata even for low-rep senders — by the
    time the operator runs ``synapse inbox review`` they have explicitly
    asked to see it.
    """
    row = store.get(task_id)
    if row is None:
        return ReviewResult(
            ok=False, task_id=task_id, sender="", sender_score=0.0,
            status="", received_at="", reason="task not found",
        )
    try:
        task = json.loads(row.task_json)
    except json.JSONDecodeError:
        return ReviewResult(
            ok=False, task_id=task_id, sender=row.sender,
            sender_score=row.sender_score, status=row.status,
            received_at=row.received_at, reason="invalid task json",
        )

    text_parts: list[str] = []
    for message in task.get("history") or []:
        for part in message.get("parts") or []:
            if part.get("kind") == "text":
                text_parts.append(str(part.get("text", "")))

    attachments: list[dict] = []
    for artifact in task.get("artifacts") or []:
        for part in artifact.get("parts") or []:
            if part.get("kind") != "file":
                continue
            file_obj = part.get("file") or {}
            entry = {
                "name": file_obj.get("name", ""),
                "mimeType": file_obj.get("mimeType", ""),
            }
            if file_obj.get("uri"):
                entry["uri"] = file_obj["uri"]
                entry["sha256"] = file_obj.get("sha256", "")
                entry["size"] = file_obj.get("size", 0)
            elif file_obj.get("bytes"):
                entry["inline_bytes"] = len(file_obj["bytes"])
            attachments.append(entry)

    return ReviewResult(
        ok=True,
        task_id=task_id,
        sender=row.sender,
        sender_score=row.sender_score,
        status=row.status,
        received_at=row.received_at,
        text="\n".join(text_parts),
        attachments=tuple(attachments),
    )


@dataclass(frozen=True)
class AcceptResult:
    ok: bool
    task_id: str
    result_sent: bool = False
    reason: str = ""
    serialized_result_payload: bytes = b""


def accept_task(
    task_id: str,
    *,
    receiver_id: str,
    store: InboxStore,
    audit: AuditLog,
    resolver: IdentityResolver,
    signer: A2ASigner,
    result_text: str = "task accepted; surfaced to local tool for execution",
) -> AcceptResult:
    """Accept a task, mark it accepted, send a result back to the sender."""
    row = store.get(task_id)
    if row is None:
        return AcceptResult(ok=False, task_id=task_id, reason="task not found")
    if row.status != "pending":
        return AcceptResult(
            ok=False, task_id=task_id, reason=f"task is {row.status}, not pending"
        )

    # Mark accepted (do not auto-execute per scope rules — surface only).
    result_payload = {
        "state": "completed",
        "message": result_text,
    }
    store.update_status(task_id, "accepted", json.dumps(result_payload))

    audit.append(
        AuditEntry(
            action="accept_task",
            sender=row.sender,
            receiver=receiver_id,
            task_id=task_id,
            timestamp=now_iso(),
            approval="accepted",
        )
    )

    # Send result back to original sender via tasks/result
    endpoint = resolver.resolve(row.sender)
    if endpoint is None:
        return AcceptResult(
            ok=True,
            task_id=task_id,
            result_sent=False,
            reason="sender endpoint unknown; result stored only",
        )

    rpc = JsonRpcRequest(
        method=METHOD_TASKS_RESULT,
        params={"taskId": task_id, "result": result_payload},
    )
    payload = rpc.to_json().encode()
    signed = signer.sign(receiver_id, payload)
    # Issue a token so the original sender's receiver lets `tasks/result` through
    # (it requires the ``a2a.send_result`` capability per Trust Model Gate 3).
    token = signer._network.issue_token(  # noqa: SLF001 — same-network access
        receiver_id, capabilities=list(DEFAULT_A2A_CAPABILITIES),
    )

    try:
        post_jsonrpc(
            endpoint.url, payload, receiver_id, signed.signature_hex,
            timestamp=signed.timestamp, token=token,
        )
    except TransportUnreachable as exc:
        audit.append(
            AuditEntry(
                action="send_result_failed",
                sender=receiver_id,
                receiver=row.sender,
                task_id=task_id,
                timestamp=now_iso(),
                detail=str(exc),
            )
        )
        return AcceptResult(
            ok=True,
            task_id=task_id,
            result_sent=False,
            reason=str(exc),
            serialized_result_payload=payload,
        )

    audit.append(
        AuditEntry(
            action="send_result",
            sender=receiver_id,
            receiver=row.sender,
            task_id=task_id,
            timestamp=now_iso(),
            signature_hash=signed.signature_hex[:16],
        )
    )

    return AcceptResult(
        ok=True, task_id=task_id, result_sent=True, serialized_result_payload=payload
    )


@dataclass(frozen=True)
class RejectResult:
    ok: bool
    task_id: str
    reason: str = ""


def reject_task(
    task_id: str,
    *,
    receiver_id: str,
    store: InboxStore,
    audit: AuditLog,
    reason: str = "",
) -> RejectResult:
    """Reject a task — logged to audit."""
    row = store.get(task_id)
    if row is None:
        return RejectResult(ok=False, task_id=task_id, reason="task not found")
    if row.status != "pending":
        return RejectResult(
            ok=False, task_id=task_id, reason=f"task is {row.status}, not pending"
        )
    store.update_status(task_id, "rejected", "")
    audit.append(
        AuditEntry(
            action="reject_task",
            sender=row.sender,
            receiver=receiver_id,
            task_id=task_id,
            timestamp=now_iso(),
            approval="rejected",
            detail=reason,
        )
    )
    return RejectResult(ok=True, task_id=task_id, reason=reason)
