# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""A2A message signer — thin wrapper around Phase B's ZeroTrustNetwork.

Signs and verifies full A2A JSON-RPC payloads using HMAC-SHA256. A
timestamp is bound into the signed bytes (``payload || b"|" || ts``) so
captured signatures cannot be replayed outside a short freshness window.
No new crypto — reuses synapse.security.zero_trust.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from synapse.security.zero_trust import ZeroTrustNetwork

#: Maximum accepted drift between the signed timestamp and receiver clock (s).
MAX_TIMESTAMP_DRIFT_SECONDS = 300


def _signed_bytes(payload: bytes, timestamp: int) -> bytes:
    """Canonical signing input: payload bytes, a separator, then the integer ts."""
    return payload + b"|" + str(int(timestamp)).encode("ascii")


@dataclass(frozen=True)
class SignedA2APayload:
    payload: bytes
    sender_id: str
    signature_hex: str
    timestamp: int


class A2ASigner:
    """Signs / verifies A2A JSON-RPC payloads using the zero-trust network."""

    def __init__(self, network: ZeroTrustNetwork) -> None:
        self._network = network

    def sign(
        self,
        sender_id: str,
        payload: bytes,
        timestamp: int | None = None,
    ) -> SignedA2APayload:
        ts = int(timestamp if timestamp is not None else time.time())
        sig = self._network.sign_payload(sender_id, _signed_bytes(payload, ts))
        return SignedA2APayload(
            payload=payload, sender_id=sender_id, signature_hex=sig, timestamp=ts
        )

    def verify(self, signed: SignedA2APayload, *, now: int | None = None) -> bool:
        return self.verify_raw(
            signed.sender_id,
            signed.payload,
            signed.signature_hex,
            signed.timestamp,
            now=now,
        )

    def verify_raw(
        self,
        sender_id: str,
        payload: bytes,
        sig_hex: str,
        timestamp: int,
        *,
        now: int | None = None,
    ) -> bool:
        current = int(now if now is not None else time.time())
        if abs(current - int(timestamp)) > MAX_TIMESTAMP_DRIFT_SECONDS:
            return False
        return self._network.verify_payload_signature(
            sender_id, _signed_bytes(payload, int(timestamp)), sig_hex
        )
