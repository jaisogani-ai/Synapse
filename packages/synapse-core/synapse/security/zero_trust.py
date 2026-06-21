# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Zero Trust agent network — JWT (HS256) identities + HMAC request signing.

Every agent has a cryptographic identity issued by the daemon. Every request is
verified: the bearer token must be valid and unexpired, the requested
capability must be granted, and (optionally) the request payload's HMAC
signature must match. No agent is implicitly trusted.

The JWT and HMAC primitives are implemented with the Python standard library
only (``hmac`` + ``hashlib`` + ``base64``) — HS256 *is* HMAC-SHA256 — so the
module has **zero external dependencies** and is fully testable offline. A
vetted library (PyJWT) can be swapped in later without changing callers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field

from synapse.security.capabilities import CapabilityError, CapabilitySet

#: Default token lifetime (seconds). Short-lived by design (15 minutes).
DEFAULT_TTL_SECONDS = 900
_ALG = "HS256"
_SECRET_BYTES = 32


class ZeroTrustError(Exception):
    """Base class for zero-trust failures."""


class InvalidSignature(ZeroTrustError):
    """The token signature did not verify, or the token is malformed."""


class TokenExpired(ZeroTrustError):
    """The token's ``exp`` is in the past."""


class UnknownAgent(ZeroTrustError):
    """No identity has been issued for the token's subject."""


def _b64url_encode(raw: bytes) -> str:
    """URL-safe base64 without padding (JWT segment encoding)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    """Inverse of :func:`_b64url_encode` (restores padding)."""
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


@dataclass(frozen=True)
class AgentIdentity:
    """An agent's cryptographic identity (its HMAC signing key)."""

    agent_id: str
    secret: bytes = field(repr=False)  # never log the key


@dataclass(frozen=True)
class Claims:
    """Decoded, verified JWT claims."""

    sub: str
    iat: int
    exp: int
    caps: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerificationResult:
    """The outcome of :meth:`ZeroTrustNetwork.verify_request`."""

    ok: bool
    reason: str
    claims: Claims | None = None


class ZeroTrustNetwork:
    """Issues agent identities/tokens and verifies every request."""

    def __init__(self) -> None:
        """Create an empty network (no identities issued yet)."""
        self._secrets: dict[str, bytes] = {}

    # ---- identity ----------------------------------------------------------

    def issue_identity(self, agent_id: str) -> AgentIdentity:
        """Issue (or rotate) a random signing key for ``agent_id``."""
        if not agent_id:
            raise ZeroTrustError("agent_id is empty")
        secret = secrets.token_bytes(_SECRET_BYTES)
        self._secrets[agent_id] = secret
        return AgentIdentity(agent_id=agent_id, secret=secret)

    def has_identity(self, agent_id: str) -> bool:
        """Whether an identity has been issued for ``agent_id``."""
        return agent_id in self._secrets

    # ---- tokens ------------------------------------------------------------

    def issue_token(
        self,
        agent_id: str,
        capabilities: list[str] | tuple[str, ...] = (),
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        *,
        now: float | None = None,
    ) -> str:
        """Issue a signed HS256 JWT for ``agent_id`` carrying ``capabilities``."""
        secret = self._secret_or_raise(agent_id)
        if ttl_seconds <= 0:
            raise ZeroTrustError("ttl_seconds must be positive")
        issued = int(now if now is not None else time.time())
        payload = {
            "sub": agent_id,
            "iat": issued,
            "exp": issued + int(ttl_seconds),
            "caps": list(capabilities),
        }
        header = {"alg": _ALG, "typ": "JWT"}
        signing_input = f"{_encode_segment(header)}.{_encode_segment(payload)}"
        signature = _b64url_encode(self._sign(signing_input.encode(), secret))
        return f"{signing_input}.{signature}"

    def verify_token(self, token: str, *, now: float | None = None) -> Claims:
        """Verify ``token`` and return its :class:`Claims`.

        Raises:
            InvalidSignature, TokenExpired, UnknownAgent.
        """
        parts = token.split(".")
        if len(parts) != 3:
            raise InvalidSignature("token must have three segments")
        header_seg, payload_seg, signature_seg = parts

        try:
            payload = json.loads(_b64url_decode(payload_seg))
        except (ValueError, json.JSONDecodeError) as exc:
            raise InvalidSignature(f"unreadable payload: {exc}") from exc

        agent_id = payload.get("sub", "")
        secret = self._secrets.get(agent_id)
        if secret is None:
            raise UnknownAgent(f"no identity for subject {agent_id!r}")

        signing_input = f"{header_seg}.{payload_seg}".encode()
        expected = _b64url_encode(self._sign(signing_input, secret))
        if not hmac.compare_digest(expected, signature_seg):
            raise InvalidSignature("signature mismatch")

        current = now if now is not None else time.time()
        if current >= payload["exp"]:
            raise TokenExpired("token expired")

        return Claims(
            sub=agent_id,
            iat=int(payload["iat"]),
            exp=int(payload["exp"]),
            caps=tuple(payload.get("caps", ())),
        )

    # ---- HMAC request signing ---------------------------------------------

    def sign_payload(self, agent_id: str, payload: bytes) -> str:
        """Return the hex HMAC-SHA256 of ``payload`` under the agent's key."""
        secret = self._secret_or_raise(agent_id)
        return self._sign(payload, secret).hex()

    def verify_payload_signature(
        self, agent_id: str, payload: bytes, signature_hex: str
    ) -> bool:
        """Constant-time check of a payload's HMAC signature."""
        try:
            expected = self.sign_payload(agent_id, payload)
        except UnknownAgent:
            return False
        return hmac.compare_digest(expected, signature_hex)

    # ---- combined request verification ------------------------------------

    def verify_request(
        self,
        token: str,
        required_capability: str,
        *,
        payload: bytes | None = None,
        signature_hex: str | None = None,
        now: float | None = None,
    ) -> VerificationResult:
        """Verify a full cross-agent request: token, capability, and signature."""
        try:
            claims = self.verify_token(token, now=now)
        except ZeroTrustError as exc:
            return VerificationResult(ok=False, reason=str(exc))

        try:
            caps = CapabilitySet.of(*claims.caps)
        except (CapabilityError, ValueError) as exc:
            return VerificationResult(
                ok=False,
                reason=f"malformed capability in token: {exc}",
                claims=claims,
            )
        if not caps.allows(required_capability):
            return VerificationResult(
                ok=False,
                reason=f"capability {required_capability!r} not granted",
                claims=claims,
            )

        if payload is not None or signature_hex is not None:
            if payload is None or signature_hex is None:
                return VerificationResult(
                    ok=False,
                    reason="both payload and signature are required to verify a body",
                    claims=claims,
                )
            if not self.verify_payload_signature(claims.sub, payload, signature_hex):
                return VerificationResult(
                    ok=False, reason="payload signature mismatch", claims=claims
                )

        return VerificationResult(ok=True, reason="verified", claims=claims)

    # ---- internals ---------------------------------------------------------

    def _secret_or_raise(self, agent_id: str) -> bytes:
        secret = self._secrets.get(agent_id)
        if secret is None:
            raise UnknownAgent(f"no identity for agent {agent_id!r}")
        return secret

    @staticmethod
    def _sign(signing_input: bytes, secret: bytes) -> bytes:
        return hmac.new(secret, signing_input, hashlib.sha256).digest()


def _encode_segment(obj: dict) -> str:
    """JSON-encode (compact, sorted) and base64url a JWT segment."""
    raw = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _b64url_encode(raw)
