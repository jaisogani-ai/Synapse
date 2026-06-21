# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Base adapter — shared identity, vault, trust, and A2A signing logic.

Every tool adapter (Claude Code, Cursor, Codex, VS Code, Antigravity) subclasses
:class:`BaseAdapter`. The base handles all cryptographic operations via the
existing ``synapse.security`` SDK; subclasses only declare their ``tool_type``.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from synapse.security.capabilities import CapabilitySet
from synapse.security.zero_trust import (
    AgentIdentity,
    ZeroTrustNetwork,
)

logger = logging.getLogger("synapse.adapter")

VAULT_MCP_URL = "synapse+vault://localhost"


@dataclass(frozen=True)
class TrustHeaders:
    """Immutable set of trust headers attached to outbound A2A messages."""

    agent_id: str
    token: str
    signature: str
    timestamp: int
    tool_type: str

    def to_dict(self) -> dict[str, str]:
        return {
            "X-Synapse-Agent": self.agent_id,
            "X-Synapse-Token": self.token,
            "X-Synapse-Signature": self.signature,
            "X-Synapse-Timestamp": str(self.timestamp),
            "X-Synapse-Tool": self.tool_type,
        }


@dataclass(frozen=True)
class VaultRequest:
    """A request to route through the vault MCP."""

    service: str
    purpose: str
    duration_seconds: int = 3600
    scope: str = ""


@dataclass(frozen=True)
class VaultResponse:
    """Response from a vault credential request."""

    proxy_url: str
    proxy_token: str
    service: str
    expires_at: str


@dataclass(frozen=True)
class AuditEntry:
    """One adapter audit log entry."""

    action: str
    agent_id: str
    tool_type: str
    timestamp: str
    detail: str = ""


@dataclass(frozen=True)
class SignedMessage:
    """An A2A message with identity signature and trust headers."""

    payload: bytes
    headers: TrustHeaders


class BaseAdapter:
    """Shared adapter logic — subclass and set ``tool_type``."""

    tool_type: str = "unknown"

    def __init__(
        self,
        agent_id: str,
        network: ZeroTrustNetwork,
        capabilities: list[str] | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._network = network
        self._identity: AgentIdentity | None = None
        self._token: str | None = None
        self._capabilities = capabilities or []
        self._audit_log: list[AuditEntry] = []
        self._registered = False

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def is_registered(self) -> bool:
        return self._registered

    def register(self) -> AgentIdentity:
        """Register this adapter's agent identity with the daemon."""
        self._identity = self._network.issue_identity(self._agent_id)
        self._token = self._network.issue_token(
            self._agent_id, self._capabilities
        )
        self._registered = True
        self._audit("register", f"tool={self.tool_type}")
        logger.info("registered agent %s (tool=%s)", self._agent_id, self.tool_type)
        return self._identity

    def sign_message(self, payload: bytes) -> SignedMessage:
        """Sign an outbound A2A message and attach trust headers."""
        if not self._registered:
            raise RuntimeError("adapter not registered — call register() first")
        assert self._token is not None

        signature = self._network.sign_payload(self._agent_id, payload)
        timestamp = int(time.time())

        headers = TrustHeaders(
            agent_id=self._agent_id,
            token=self._token,
            signature=signature,
            timestamp=timestamp,
            tool_type=self.tool_type,
        )

        self._audit("sign_message", f"payload_size={len(payload)}")
        return SignedMessage(payload=payload, headers=headers)

    def verify_message(self, message: SignedMessage) -> bool:
        """Verify an inbound signed message."""
        return self._network.verify_payload_signature(
            message.headers.agent_id,
            message.payload,
            message.headers.signature,
        )

    def request_vault_credential(self, request: VaultRequest) -> VaultResponse:
        """Route a credential request through the vault MCP."""
        if not self._registered:
            raise RuntimeError("adapter not registered — call register() first")

        self._audit(
            "vault_request",
            f"service={request.service} purpose={request.purpose}",
        )

        return VaultResponse(
            proxy_url=f"{VAULT_MCP_URL}/proxy/{request.service}",
            proxy_token=f"pending:{request.service}",
            service=request.service,
            expires_at="",
        )

    def build_trust_headers(self, payload: bytes | None = None) -> TrustHeaders:
        """Build trust headers for an outbound request."""
        if not self._registered:
            raise RuntimeError("adapter not registered — call register() first")
        assert self._token is not None

        signature = ""
        if payload is not None:
            signature = self._network.sign_payload(self._agent_id, payload)

        return TrustHeaders(
            agent_id=self._agent_id,
            token=self._token,
            signature=signature,
            timestamp=int(time.time()),
            tool_type=self.tool_type,
        )

    def audit_log(self) -> list[AuditEntry]:
        """Return copy of audit log."""
        return list(self._audit_log)

    def _audit(self, action: str, detail: str = "") -> None:
        entry = AuditEntry(
            action=action,
            agent_id=self._agent_id,
            tool_type=self.tool_type,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            detail=detail,
        )
        self._audit_log = [*self._audit_log, entry]
        logger.debug("audit: %s %s %s", action, self._agent_id, detail)
