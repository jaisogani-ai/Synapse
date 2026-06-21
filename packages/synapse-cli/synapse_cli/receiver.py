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


@dataclass
class ReceivingDaemon:
    """Stateful receiver that handles signed A2A JSON-RPC requests."""

    receiver_id: str
    signer: A2ASigner
    trust: TrustStore
    inbox: InboxStore
    audit: AuditLog

    def handle_request(
        self, body: bytes, sender_id: str, signature_hex: str,
        timestamp: str = "",
    ) -> dict[str, Any]:
        # ── 1. Reject unsigned / missing-sender messages immediately ──
        if not sender_id or not signature_hex:
            self._audit_reject("missing_sender_or_signature", sender_id, "")
            return self._error_response("unsigned or missing sender")

        # ── 2. Parse + verify timestamp (replay window) ──
        try:
            ts_int = int(timestamp) if timestamp else 0
        except ValueError:
            ts_int = 0
        if ts_int == 0:
            self._audit_reject("missing_timestamp", sender_id, "")
            return self._error_response("missing or invalid timestamp")

        # ── 3. Verify signature over (payload || timestamp) ──
        if not self.signer.verify_raw(sender_id, body, signature_hex, ts_int):
            self._audit_reject("bad_signature_or_stale", sender_id, "")
            return self._error_response("signature verification failed or message stale")

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

        # ── 4. Dispatch ──
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

    def _error_response(
        self, message: str, req_id: str = ""
    ) -> dict[str, Any]:
        return JsonRpcResponse(
            id=req_id, error={"code": -32000, "message": message}
        ).to_dict()
