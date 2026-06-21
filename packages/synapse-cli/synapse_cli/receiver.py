# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Receiving daemon — handles inbound A2A messages.

Flow:
  1. Verify signature via a2a_signer (rejects silently-failing/unsigned)
  2. Look up sender reputation via trust
  3. Store task in inbox SQLite (pending state)
  4. Write audit entry
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from synapse.security.quarantine import QuarantineStore
from synapse.security.threat_response import FailureTracker
from synapse.security.zero_trust import ZeroTrustNetwork

from .a2a import (
    JsonRpcResponse,
    METHOD_MESSAGE_SEND,
    METHOD_TASKS_GET,
    METHOD_TASKS_RESULT,
)
from .a2a_signer import A2ASigner
from .audit import AuditEntry, AuditLog, now_iso
from .inbox_store import DuplicateTaskError, InboxStore
from .trust import TrustStore

#: Required capability per A2A method. The receiver consults this table for
#: every inbound JSON-RPC and rejects requests whose token does not grant the
#: required capability (Gate 3 of the Trust Model).
METHOD_REQUIRED_CAPABILITY: dict[str, str] = {
    METHOD_MESSAGE_SEND: "a2a.send_task",
    METHOD_TASKS_RESULT: "a2a.send_result",
    METHOD_TASKS_GET: "a2a.read_status",
}


@dataclass
class ReceivingDaemon:
    """Stateful receiver that handles signed A2A JSON-RPC requests.

    Gate 3 (capability enforcement) is wired in here: every dispatched method
    consults :data:`METHOD_REQUIRED_CAPABILITY` and rejects the request if the
    sender's signed token does not grant the required capability. Set
    ``enforce_capabilities=False`` for tests that exercise the bare A2A path
    against a legacy peer (this fallback never ships in the CLI default).
    """

    receiver_id: str
    signer: A2ASigner
    trust: TrustStore
    inbox: InboxStore
    audit: AuditLog
    network: ZeroTrustNetwork | None = None
    enforce_capabilities: bool = True
    quarantine: QuarantineStore | None = None
    failure_tracker: FailureTracker | None = None

    def __post_init__(self) -> None:
        # If no network was injected, reuse the signer's. They share secrets
        # so a token issued by one verifies on the other.
        if self.network is None:
            self.network = self.signer._network  # noqa: SLF001 — intentional
        # In-process per-agent failure counter; opt-in for receivers that care.
        if self.failure_tracker is None:
            self.failure_tracker = FailureTracker()

    def handle_request(
        self, body: bytes, sender_id: str, signature_hex: str,
        timestamp: str = "", token: str = "",
    ) -> dict[str, Any]:
        # ── 0. Quarantine pre-check ──
        if self.quarantine is not None and sender_id and self.quarantine.is_quarantined(sender_id):
            self._audit_reject("quarantined", sender_id, "")
            return self._error_response("sender is quarantined")

        # ── 1. Reject unsigned / missing-sender messages immediately ──
        if not sender_id or not signature_hex:
            self._audit_reject("missing_sender_or_signature", sender_id, "")
            self._record_gate1_failure(sender_id)
            return self._error_response("unsigned or missing sender")

        # ── 2. Parse + verify timestamp (replay window) ──
        try:
            ts_int = int(timestamp) if timestamp else 0
        except ValueError:
            ts_int = 0
        if ts_int == 0:
            self._audit_reject("missing_timestamp", sender_id, "")
            self._record_gate1_failure(sender_id)
            return self._error_response("missing or invalid timestamp")

        # ── 3. Verify signature over (payload || timestamp) ──
        if not self.signer.verify_raw(sender_id, body, signature_hex, ts_int):
            self._audit_reject("bad_signature_or_stale", sender_id, "")
            self._record_gate1_failure(sender_id)
            return self._error_response("signature verification failed or message stale")
        # Gate 1 passed — reset the failure counter so transient noise doesn't quarantine.
        assert self.failure_tracker is not None
        self.failure_tracker.record_success(sender_id)

        # ── 3. Parse JSON-RPC ──
        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self._audit_reject("bad_json", sender_id, "")
            return self._error_response("invalid JSON")

        if not isinstance(request, dict):
            self._audit_reject("malformed_envelope", sender_id, "")
            return self._error_response("envelope must be a JSON object")

        method = request.get("method", "")
        params = request.get("params") or {}
        req_id = request.get("id", "")

        if not isinstance(params, dict):
            self._audit_reject("malformed_params", sender_id, "")
            return self._error_response("params must be a JSON object", req_id)

        # ── 4. Capability gate (Trust Model Gate 3) ──
        if self.enforce_capabilities:
            required = METHOD_REQUIRED_CAPABILITY.get(method)
            if required is not None:
                cap_ok, cap_reason = self._check_capability(
                    token, sender_id, required
                )
                if not cap_ok:
                    self.audit.append(
                        AuditEntry(
                            action="reject_capability",
                            sender=sender_id,
                            receiver=self.receiver_id,
                            task_id="<no-task>",
                            timestamp=now_iso(),
                            approval="rejected",
                            detail=f"method={method} required={required} reason={cap_reason}",
                        )
                    )
                    return self._error_response(
                        f"capability denied: {cap_reason}", req_id
                    )

        # ── 5. Dispatch ──
        if method == METHOD_MESSAGE_SEND:
            return self._handle_message_send(params, req_id, sender_id, signature_hex)
        if method == METHOD_TASKS_GET:
            return self._handle_tasks_get(params, req_id)
        if method == METHOD_TASKS_RESULT:
            return self._handle_tasks_result(params, req_id, sender_id)

        return JsonRpcResponse(
            id=req_id,
            error={"code": -32601, "message": f"method not found: {method}"},
        ).to_dict()

    def _check_capability(
        self, token: str, sender_id: str, required: str
    ) -> tuple[bool, str]:
        """Verify the sender's token grants the required capability.

        Returns ``(ok, reason)``. We require the token's ``sub`` to equal the
        HMAC-asserted ``sender_id`` so a valid token from agent A cannot be
        replayed by agent B even if B successfully forges the HMAC (defence
        in depth — the HMAC verify already prevents that).
        """
        if not token:
            return False, "missing X-A2A-Token"
        assert self.network is not None
        result = self.network.verify_request(token, required)
        if not result.ok:
            return False, result.reason
        if result.claims is None or result.claims.sub != sender_id:
            return False, "token subject does not match sender"
        return True, "ok"

    # ── method handlers ────────────────────────────────────────────────

    def _handle_message_send(
        self, params: dict[str, Any], req_id: str, sender_id: str, signature_hex: str
    ) -> dict[str, Any]:
        task = params.get("task") or {}
        if not isinstance(task, dict):
            return self._error_response("task must be a JSON object", req_id)
        task_id = task.get("id", "")
        if not isinstance(task_id, str) or not task_id:
            return self._error_response("missing task.id", req_id)

        sender_score = self.trust.get_score(sender_id)

        # Low-rep senders: still queue (so it's not silently dropped),
        # but mark explicitly so 'inbox' won't reveal full content
        # without explicit accept.
        try:
            self.inbox.insert(
                task_id=task_id,
                sender=sender_id,
                task_dict=task,
                signature=signature_hex,
                sender_score=sender_score,
            )
        except DuplicateTaskError:
            self.audit.append(
                AuditEntry(
                    action="reject_replay",
                    sender=sender_id,
                    receiver=self.receiver_id,
                    task_id=task_id,
                    timestamp=now_iso(),
                    signature_hash=signature_hex[:16],
                    approval="rejected",
                    detail="duplicate task_id",
                )
            )
            return self._error_response("duplicate task_id (replay)", req_id)

        self.audit.append(
            AuditEntry(
                action="receive_task",
                sender=sender_id,
                receiver=self.receiver_id,
                task_id=task_id,
                timestamp=now_iso(),
                signature_hash=signature_hex[:16],
                approval="pending",
                detail=f"score={sender_score}",
            )
        )

        return JsonRpcResponse(
            id=req_id,
            result={"taskId": task_id, "status": {"state": "submitted"}},
        ).to_dict()

    def _handle_tasks_get(
        self, params: dict[str, Any], req_id: str
    ) -> dict[str, Any]:
        task_id = params.get("id", "")
        if not isinstance(task_id, str) or not task_id:
            return self._error_response("missing or invalid task id", req_id)
        row = self.inbox.get(task_id)
        if row is None:
            return self._error_response("task not found", req_id)
        return JsonRpcResponse(
            id=req_id,
            result={"id": task_id, "status": {"state": row.status}},
        ).to_dict()

    def _handle_tasks_result(
        self, params: dict[str, Any], req_id: str, sender_id: str
    ) -> dict[str, Any]:
        """Receive a result message coming back from the original receiver."""
        task_id = params.get("taskId", "")
        if not isinstance(task_id, str) or not task_id:
            return self._error_response("missing or invalid taskId", req_id)
        result = params.get("result") or {}
        if not isinstance(result, dict):
            return self._error_response("result must be a JSON object", req_id)
        row = self.inbox.get(task_id)
        if row is not None:
            self.inbox.update_status(task_id, "completed", json.dumps(result))
        self.audit.append(
            AuditEntry(
                action="receive_result",
                sender=sender_id,
                receiver=self.receiver_id,
                task_id=task_id,
                timestamp=now_iso(),
                detail=json.dumps(result)[:80],
            )
        )
        return JsonRpcResponse(id=req_id, result={"ack": True}).to_dict()

    # ── helpers ────────────────────────────────────────────────────────

    def _audit_reject(self, reason: str, sender_id: str, task_id: str) -> None:
        self.audit.append(
            AuditEntry(
                action="reject_unsigned",
                sender=sender_id or "<unknown>",
                receiver=self.receiver_id,
                task_id=task_id or "<no-task>",
                timestamp=now_iso(),
                approval="rejected",
                detail=reason,
            )
        )

    def _record_gate1_failure(self, sender_id: str) -> None:
        """Track Gate-1 failures and auto-quarantine after the threshold."""
        if not sender_id:
            return
        assert self.failure_tracker is not None
        self.failure_tracker.record_failure(sender_id)
        if self.failure_tracker.should_block(sender_id) and self.quarantine is not None:
            if not self.quarantine.is_quarantined(sender_id):
                self.quarantine.quarantine(
                    sender_id,
                    reason=(
                        f"auto: {self.failure_tracker.count_for(sender_id)} "
                        "consecutive Gate-1 failures"
                    ),
                    at=now_iso(),
                )
                self.audit.append(
                    AuditEntry(
                        action="auto_quarantine",
                        sender=sender_id,
                        receiver=self.receiver_id,
                        task_id="<no-task>",
                        timestamp=now_iso(),
                        approval="rejected",
                        detail="threat-response auto-block",
                    )
                )

    def _error_response(
        self, message: str, req_id: str = ""
    ) -> dict[str, Any]:
        return JsonRpcResponse(
            id=req_id, error={"code": -32000, "message": message}
        ).to_dict()
