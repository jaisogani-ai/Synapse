# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""End-to-end encryption — sealed-box round-trip + tamper / wrong-key rejection.

These tests use the real `cryptography` X25519 + AES-GCM primitives. They pin
the contract: a sealed envelope round-trips for the right recipient, and
fails closed for everyone and everything else.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from synapse_cli.e2e import (
    E2E_ALG,
    E2E_VERSION,
    E2EError,
    PublicKeyRegistry,
    generate_keypair,
    is_encrypted_envelope,
    load_private_key,
    load_public_key,
    seal,
    unseal,
)


def _keypair(agent_id: str, tmp_path: Path):
    files = generate_keypair(agent_id, tmp_path / "keys")
    return load_private_key(files.private_path), load_public_key(files.public_path)


# ── key generation ──────────────────────────────────────────────────────────


def test_generate_keypair_writes_pem_files(tmp_path: Path) -> None:
    files = generate_keypair("alice", tmp_path / "keys")
    assert files.private_path.exists()
    assert files.public_path.exists()
    assert files.private_path.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")
    assert files.public_path.read_bytes().startswith(b"-----BEGIN PUBLIC KEY-----")


def test_generate_keypair_rejects_empty_agent_id(tmp_path: Path) -> None:
    with pytest.raises(E2EError):
        generate_keypair("", tmp_path / "keys")


def test_load_private_key_rejects_public_pem(tmp_path: Path) -> None:
    files = generate_keypair("alice", tmp_path / "keys")
    with pytest.raises(E2EError):
        load_private_key(files.public_path)  # public PEM is not a private key


# ── seal / unseal round-trip ────────────────────────────────────────────────


def test_seal_unseal_round_trip(tmp_path: Path) -> None:
    bob_priv, bob_pub = _keypair("bob", tmp_path)
    plaintext = b'{"task": "review auth module", "secret": false}'

    envelope = seal(plaintext, bob_pub, sender_id="alice", recipient_id="bob")
    assert envelope["v"] == E2E_VERSION
    assert envelope["alg"] == E2E_ALG
    assert envelope["sender"] == "alice"
    assert envelope["recipient"] == "bob"

    recovered = unseal(envelope, bob_priv)
    assert recovered == plaintext


def test_ciphertext_does_not_contain_plaintext(tmp_path: Path) -> None:
    _, bob_pub = _keypair("bob", tmp_path)
    secret = b"TOP-SECRET-PAYLOAD-DO-NOT-LEAK"
    envelope = seal(secret, bob_pub, sender_id="alice", recipient_id="bob")
    blob = (envelope["ct"] + envelope["epk"] + envelope["nonce"]).encode()
    assert secret not in blob
    assert secret not in base64.b64decode(envelope["ct"])


def test_each_seal_uses_fresh_ephemeral_key(tmp_path: Path) -> None:
    """Forward secrecy: two seals of the same plaintext differ entirely."""
    _, bob_pub = _keypair("bob", tmp_path)
    e1 = seal(b"same", bob_pub, "alice", "bob")
    e2 = seal(b"same", bob_pub, "alice", "bob")
    assert e1["epk"] != e2["epk"]
    assert e1["ct"] != e2["ct"]
    assert e1["nonce"] != e2["nonce"]


# ── failure paths ────────────────────────────────────────────────────────────


def test_wrong_recipient_key_cannot_decrypt(tmp_path: Path) -> None:
    _, bob_pub = _keypair("bob", tmp_path)
    eve_priv, _ = _keypair("eve", tmp_path)
    envelope = seal(b"for bob only", bob_pub, "alice", "bob")
    with pytest.raises(E2EError):
        unseal(envelope, eve_priv)  # Eve's key can't open Bob's envelope


def test_tampered_ciphertext_is_rejected(tmp_path: Path) -> None:
    bob_priv, bob_pub = _keypair("bob", tmp_path)
    envelope = seal(b"original", bob_pub, "alice", "bob")
    raw = bytearray(base64.b64decode(envelope["ct"]))
    raw[0] ^= 0xFF  # flip a bit
    envelope["ct"] = base64.b64encode(bytes(raw)).decode()
    with pytest.raises(E2EError):
        unseal(envelope, bob_priv)


def test_sender_mismatch_is_rejected(tmp_path: Path) -> None:
    """The (sender, recipient) pair is bound into the AAD; changing it fails."""
    bob_priv, bob_pub = _keypair("bob", tmp_path)
    envelope = seal(b"hi", bob_pub, "alice", "bob")
    envelope["sender"] = "mallory"  # attacker rewrites the sender claim
    with pytest.raises(E2EError):
        unseal(envelope, bob_priv)


def test_recipient_mismatch_is_rejected(tmp_path: Path) -> None:
    bob_priv, bob_pub = _keypair("bob", tmp_path)
    envelope = seal(b"hi", bob_pub, "alice", "bob")
    envelope["recipient"] = "carol"
    with pytest.raises(E2EError):
        unseal(envelope, bob_priv)


def test_unsupported_version_rejected(tmp_path: Path) -> None:
    bob_priv, bob_pub = _keypair("bob", tmp_path)
    envelope = seal(b"hi", bob_pub, "alice", "bob")
    envelope["v"] = 999
    with pytest.raises(E2EError):
        unseal(envelope, bob_priv)


def test_malformed_envelope_rejected(tmp_path: Path) -> None:
    bob_priv, _ = _keypair("bob", tmp_path)
    with pytest.raises(E2EError):
        unseal({"v": E2E_VERSION, "alg": E2E_ALG}, bob_priv)  # missing fields


# ── envelope detection ───────────────────────────────────────────────────────


def test_is_encrypted_envelope_detects_real_envelope(tmp_path: Path) -> None:
    _, bob_pub = _keypair("bob", tmp_path)
    envelope = seal(b"hi", bob_pub, "alice", "bob")
    assert is_encrypted_envelope(envelope)
    assert not is_encrypted_envelope({"jsonrpc": "2.0", "method": "message/send"})
    assert not is_encrypted_envelope("not a dict")


# ── public-key registry ──────────────────────────────────────────────────────


def test_public_key_registry_resolves_and_lists(tmp_path: Path) -> None:
    key_dir = tmp_path / "pubkeys"
    generate_keypair("alice", key_dir)
    generate_keypair("bob", key_dir)
    reg = PublicKeyRegistry(key_dir)
    assert reg.has("alice")
    assert reg.has("bob")
    assert not reg.has("eve")
    assert reg.list_agents() == ["alice", "bob"]
    # resolves to a usable public key
    pub = reg.get("alice")
    envelope = seal(b"ping", pub, "bob", "alice")
    assert envelope["recipient"] == "alice"


def test_public_key_registry_missing_agent_raises(tmp_path: Path) -> None:
    reg = PublicKeyRegistry(tmp_path / "pubkeys")
    with pytest.raises(E2EError):
        reg.get("nobody")


def test_full_pipeline_through_registry(tmp_path: Path) -> None:
    """Realistic flow: alice seals to bob using bob's pubkey from a registry,
    bob unseals with his private key."""
    key_dir = tmp_path / "keys"
    bob_files = generate_keypair("bob", key_dir)
    reg = PublicKeyRegistry(key_dir)

    message = b'{"history": [{"role": "user", "parts": [{"kind": "text", "text": "task"}]}]}'
    envelope = seal(message, reg.get("bob"), sender_id="alice", recipient_id="bob")

    bob_priv = load_private_key(bob_files.private_path)
    assert unseal(envelope, bob_priv) == message


def test_send_task_end_to_end_encrypted_into_receiver(tmp_path: Path) -> None:
    """Regression: the full send_task → receiver path with E2E on.

    Proves the wire payload is ciphertext, the receiver with the private key
    decrypts and stores the task, and a receiver WITHOUT the key fails closed.
    """
    from synapse.security.zero_trust import ZeroTrustNetwork
    from synapse_cli.a2a_signer import A2ASigner
    from synapse_cli.audit import AuditLog
    from synapse_cli.inbox_store import InboxStore
    from synapse_cli.receiver import ReceivingDaemon
    from synapse_cli.trust import TrustStore

    bob_files = generate_keypair("bob", tmp_path / "keys")
    bob_pub = load_public_key(bob_files.public_path)
    bob_priv = load_private_key(bob_files.private_path)

    network = ZeroTrustNetwork()
    network.issue_identity("alice")
    network.issue_identity("bob")
    bob_inbox = InboxStore(tmp_path / "bob_inbox.db")
    bob_trust = TrustStore(tmp_path / "bob_trust.json")
    bob_trust.set_score("alice", 0.9)
    receiver = ReceivingDaemon(
        receiver_id="bob",
        signer=A2ASigner(network),
        trust=bob_trust,
        inbox=bob_inbox,
        audit=AuditLog(tmp_path / "bob_audit.jsonl"),
        e2e_private_key=bob_priv,
    )

    # Build the encrypted body exactly as send_task does, then feed the
    # receiver directly — this exercises the decrypt path without the HTTP hop.
    secret = "review the billing service quietly"
    # Build the encrypted body exactly as send_task does, then feed the receiver.
    from synapse_cli.a2a import (
        JsonRpcRequest,
        METHOD_MESSAGE_SEND,
        Message,
        Task,
        TaskStatus,
        TextPart,
        new_context_id,
        new_task_id,
    )

    tid = new_task_id()
    task = Task(
        id=tid,
        context_id=new_context_id(),
        status=TaskStatus(state="submitted", timestamp=""),
        history=(Message(role="user", parts=(TextPart(text=secret),)),),
    )
    rpc = JsonRpcRequest(method=METHOD_MESSAGE_SEND, params={"task": task.to_dict()})
    inner = rpc.to_json().encode()
    envelope = seal(inner, bob_pub, sender_id="alice", recipient_id="bob")
    import json as _json

    wire = _json.dumps(envelope, separators=(",", ":")).encode()
    assert secret.encode() not in wire  # ciphertext on the wire

    ts = str(int(__import__("time").time()))
    sig = A2ASigner(network).sign("alice", wire).signature_hex
    token = network.issue_token("alice", capabilities=["a2a.send_task"])

    resp = receiver.handle_request(wire, "alice", sig, timestamp=ts, token=token)
    assert resp.get("result", {}).get("taskId") == tid
    rows = bob_inbox.list_all()
    assert len(rows) == 1
    decoded = _json.loads(rows[0].task_json)
    assert decoded["history"][0]["parts"][0]["text"] == secret

    # Keyless receiver fails closed
    keyless = ReceivingDaemon(
        receiver_id="bob",
        signer=A2ASigner(network),
        trust=bob_trust,
        inbox=InboxStore(tmp_path / "keyless_inbox.db"),
        audit=AuditLog(tmp_path / "keyless_audit.jsonl"),
        e2e_private_key=None,
    )
    ts2 = str(int(__import__("time").time()))
    sig2 = A2ASigner(network).sign("alice", wire).signature_hex
    resp2 = keyless.handle_request(wire, "alice", sig2, timestamp=ts2, token=token)
    assert "error" in resp2
    assert "no key" in resp2["error"]["message"]
