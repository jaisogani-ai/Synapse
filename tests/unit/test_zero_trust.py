# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Unit tests for the Zero Trust network (JWT + HMAC)."""

from __future__ import annotations

import pytest

from synapse.security.zero_trust import (
    InvalidSignature,
    TokenExpired,
    UnknownAgent,
    ZeroTrustNetwork,
)


def test_issue_and_verify_token_round_trip() -> None:
    net = ZeroTrustNetwork()
    net.issue_identity("agent-1")
    token = net.issue_token("agent-1", capabilities=["trust.read"], now=1000)
    claims = net.verify_token(token, now=1100)
    assert claims.sub == "agent-1"
    assert "trust.read" in claims.caps


def test_tampered_token_is_rejected() -> None:
    net = ZeroTrustNetwork()
    net.issue_identity("a")
    token = net.issue_token("a", now=1000)
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    with pytest.raises(InvalidSignature):
        net.verify_token(tampered, now=1100)


def test_expired_token_raises() -> None:
    net = ZeroTrustNetwork()
    net.issue_identity("a")
    token = net.issue_token("a", ttl_seconds=60, now=1000)
    with pytest.raises(TokenExpired):
        net.verify_token(token, now=2000)


def test_unknown_subject_raises() -> None:
    issuer = ZeroTrustNetwork()
    issuer.issue_identity("a")
    token = issuer.issue_token("a", now=1000)
    # A different network has never heard of "a".
    other = ZeroTrustNetwork()
    with pytest.raises(UnknownAgent):
        other.verify_token(token, now=1100)


def test_hmac_payload_signing() -> None:
    net = ZeroTrustNetwork()
    net.issue_identity("a")
    payload = b'{"op":"write"}'
    sig = net.sign_payload("a", payload)
    assert net.verify_payload_signature("a", payload, sig)
    assert not net.verify_payload_signature("a", b"tampered", sig)


def test_verify_request_enforces_capability_and_signature() -> None:
    net = ZeroTrustNetwork()
    net.issue_identity("a")
    token = net.issue_token("a", capabilities=["trust.*"], now=1000)
    payload = b"body"
    sig = net.sign_payload("a", payload)

    ok = net.verify_request(
        token, "trust.write", payload=payload, signature_hex=sig, now=1100
    )
    assert ok.ok, ok.reason

    missing_cap = net.verify_request(token, "vault.revoke", now=1100)
    assert not missing_cap.ok
    assert "not granted" in missing_cap.reason

    bad_sig = net.verify_request(
        token, "trust.write", payload=payload, signature_hex="deadbeef", now=1100
    )
    assert not bad_sig.ok
