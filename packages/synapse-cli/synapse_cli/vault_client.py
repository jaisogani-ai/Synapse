# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Vault client — issues scoped proxy tokens for credential-touching tasks.

Routes raw credentials away from the A2A wire by replacing them with a
short-lived proxy reference. The receiving daemon resolves the proxy via the
vault MCP — the raw value never appears in the task payload.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass


#: Keywords that mark a task as credential-touching.
CREDENTIAL_KEYWORDS = ("deploy", "prod", "secret", "key", "credential", "token")


@dataclass(frozen=True)
class VaultProxyToken:
    proxy_url: str
    proxy_token: str
    service: str
    expires_at: float
    ttl: int


def is_credential_touching(task_text: str) -> bool:
    """Lightweight keyword detector for credential-touching tasks."""
    lower = task_text.lower()
    return any(kw in lower for kw in CREDENTIAL_KEYWORDS)


class VaultClient:
    """In-memory vault client for CLI use — mirrors the MCP server."""

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}
        self._proxies: dict[str, tuple[str, float]] = {}

    def store(self, service: str, value: str) -> None:
        self._secrets[service] = value

    def has(self, service: str) -> bool:
        return service in self._secrets

    def request_proxy(
        self, service: str, ttl: int = 300
    ) -> VaultProxyToken:
        if service not in self._secrets:
            # Allow proxy-only mode — caller may not have raw secret locally
            # but daemon will resolve later. We still issue a token.
            pass
        token = secrets.token_hex(24)
        expires = time.time() + ttl
        self._proxies[token] = (service, expires)
        return VaultProxyToken(
            proxy_url=f"synapse+vault://proxy/{token}",
            proxy_token=token,
            service=service,
            expires_at=expires,
            ttl=ttl,
        )

    def resolve(self, token: str) -> str | None:
        entry = self._proxies.get(token)
        if not entry:
            return None
        service, expires = entry
        if time.time() >= expires:
            return None
        return self._secrets.get(service)
