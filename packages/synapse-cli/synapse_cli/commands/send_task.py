# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""`synapse send-task` — send an A2A task to a remote agent.

Flow:
  1. Resolve <agent-id> via identity_resolver
  2. Presence check — fail fast if unreachable
  3. Pull target reputation; warn / require --confirm if below threshold
  4. Detect credential-touching tasks; route via vault proxy; require approval
  5. Build standard A2A Task per spec
  6. Attach --file as A2A artifact (text/file part)
  7. Sign with a2a_signer (reuses ZeroTrustNetwork)
  8. Send via JSON-RPC over HTTP
  9. Write audit entry
"""

from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..a2a import (
    Artifact,
    DataPart,
    FilePart,
    JsonRpcRequest,
    Message,
    METHOD_MESSAGE_SEND,
    Part,
    Task,
    TaskStatus,
    TextPart,
    new_context_id,
    new_task_id,
)
from ..a2a_signer import A2ASigner
from ..audit import AuditEntry, AuditLog, now_iso
from ..identity_resolver import IdentityResolver
from ..transport import TransportUnreachable, is_reachable, post_jsonrpc
from ..trust import DEFAULT_TRUST_THRESHOLD, TrustStore
from ..vault_client import VaultClient, is_credential_touching

#: Hard cap on a single attached artifact (10 MiB). Prevents OOM on either side.
MAX_ARTIFACT_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class SendResult:
    ok: bool
    task_id: str
    reason: str = ""
    serialized_payload: bytes = b""
    response: dict[str, Any] | None = None


@dataclass(frozen=True)
class SendOptions:
    sender_id: str
    target_id: str
    task_text: str
    file_path: Path | None = None
    confirm: bool = False
    trust_threshold: float = DEFAULT_TRUST_THRESHOLD
    credential_service: str = ""  # if set, vault proxy is requested


def send_task(
    opts: SendOptions,
    *,
    resolver: IdentityResolver,
    trust: TrustStore,
    signer: A2ASigner,
    vault: VaultClient,
    audit: AuditLog,
    confirm_fn: Callable[[str], bool] | None = None,
    reachable_fn: Callable[[str], bool] | None = None,
) -> SendResult:
    """Pure function — all collaborators injected so it's trivially testable."""

    # ── 1. Resolve target endpoint ───────────────────────────────────
    endpoint = resolver.resolve(opts.target_id)
    if endpoint is None:
        return SendResult(ok=False, task_id="", reason=f"unknown agent: {opts.target_id}")

    # ── 2. Presence check — fail fast, no offline queue ──────────────
    check_fn = reachable_fn or is_reachable
    if not check_fn(endpoint.url):
        return SendResult(
            ok=False,
            task_id="",
            reason=f"target unreachable: {endpoint.url} (no offline queue in v1)",
        )

    # ── 3. Reputation check ──────────────────────────────────────────
    target_score = trust.get_score(opts.target_id)
    low_rep = target_score < opts.trust_threshold
    if low_rep and not opts.confirm:
        ask = confirm_fn or (lambda _msg: False)
        if not ask(
            f"target {opts.target_id} reputation {target_score:.2f} < "
            f"{opts.trust_threshold:.2f}; send anyway?"
        ):
            return SendResult(
                ok=False, task_id="", reason="low reputation; not confirmed"
            )

    # ── 4. Credential-touching detection + vault proxy routing ───────
    is_cred = is_credential_touching(opts.task_text)
    proxy_token = None
    if is_cred:
        # Require approval gate regardless of reputation
        ask = confirm_fn or (lambda _msg: False)
        if not opts.confirm and not ask(
            f"credential-touching task: {opts.task_text!r} — approve send?"
        ):
            return SendResult(
                ok=False, task_id="", reason="credential task not approved"
            )
        if opts.credential_service:
            proxy_token = vault.request_proxy(opts.credential_service, ttl=300)

    # ── 5. Build standard A2A Task ───────────────────────────────────
    parts: list[Part] = [TextPart(text=opts.task_text)]

    if proxy_token is not None:
        # Vault proxy carried as a data part — never the raw secret
        parts.append(
            DataPart(
                data={
                    "vaultProxy": {
                        "proxyUrl": proxy_token.proxy_url,
                        "proxyToken": proxy_token.proxy_token,
                        "service": proxy_token.service,
                        "ttl": proxy_token.ttl,
                    }
                }
            )
        )

    artifacts: tuple[Artifact, ...] = ()
    if opts.file_path is not None:
        size = opts.file_path.stat().st_size
        if size > MAX_ARTIFACT_BYTES:
            return SendResult(
                ok=False,
                task_id="",
                reason=f"file too large: {size} bytes (max {MAX_ARTIFACT_BYTES})",
            )
        file_bytes = opts.file_path.read_bytes()
        mime, _ = mimetypes.guess_type(opts.file_path.name)
        artifacts = (
            Artifact(
                artifact_id=str(opts.file_path.name),
                name=opts.file_path.name,
                parts=(
                    FilePart(
                        name=opts.file_path.name,
                        mime_type=mime or "application/octet-stream",
                        bytes=base64.b64encode(file_bytes).decode("ascii"),
                    ),
                ),
            ),
        )

    task_id = new_task_id()
    task = Task(
        id=task_id,
        context_id=new_context_id(),
        status=TaskStatus(state="submitted", timestamp=now_iso()),
        history=(Message(role="user", parts=tuple(parts)),),
        artifacts=artifacts,
    )

    # ── 6. Build JSON-RPC envelope ──────────────────────────────────
    rpc = JsonRpcRequest(
        method=METHOD_MESSAGE_SEND,
        params={"task": task.to_dict()},
    )
    payload = rpc.to_json().encode()

    # ── 7. Sign the full payload (timestamp bound into signature) ────
    signed = signer.sign(opts.sender_id, payload)

    # ── 8. Send ──────────────────────────────────────────────────────
    try:
        response = post_jsonrpc(
            endpoint.url, payload, opts.sender_id, signed.signature_hex,
            timestamp=signed.timestamp,
        )
    except TransportUnreachable as exc:
        audit.append(
            AuditEntry(
                action="send_task_failed",
                sender=opts.sender_id,
                receiver=opts.target_id,
                task_id=task_id,
                timestamp=now_iso(),
                detail=str(exc),
            )
        )
        return SendResult(
            ok=False, task_id=task_id, reason=str(exc), serialized_payload=payload
        )

    # ── 9. Audit ─────────────────────────────────────────────────────
    audit.append(
        AuditEntry(
            action="send_task",
            sender=opts.sender_id,
            receiver=opts.target_id,
            task_id=task_id,
            timestamp=now_iso(),
            signature_hash=signed.signature_hex[:16],
            approval="confirmed" if opts.confirm or low_rep or is_cred else "auto",
            detail=f"text={opts.task_text[:40]} cred={is_cred}",
        )
    )

    return SendResult(
        ok=True, task_id=task_id, serialized_payload=payload, response=response
    )
