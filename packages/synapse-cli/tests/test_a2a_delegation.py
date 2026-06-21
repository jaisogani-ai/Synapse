# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""End-to-end tests for A2A task delegation.

Spins up two local daemon instances (different ports — laptop + VPS sim)
and exercises the full send → receive → accept → result-back flow.
"""

from __future__ import annotations

import socket
import time
from pathlib import Path

import pytest

from synapse.security.zero_trust import ZeroTrustNetwork
from synapse_cli.a2a_signer import A2ASigner
from synapse_cli.audit import AuditLog
from synapse_cli.commands.inbox import accept_task, list_inbox
from synapse_cli.commands.send_task import SendOptions, send_task
from synapse_cli.identity_resolver import IdentityResolver
from synapse_cli.inbox_store import InboxStore
from synapse_cli.receiver import ReceivingDaemon
from synapse_cli.transport import A2AServer
from synapse_cli.trust import TrustStore
from synapse_cli.vault_client import VaultClient


# ─── helpers ─────────────────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def shared_network() -> ZeroTrustNetwork:
    """Single zero-trust network — laptop & VPS know each other's keys."""
    return ZeroTrustNetwork()


@pytest.fixture
def signer(shared_network: ZeroTrustNetwork) -> A2ASigner:
    return A2ASigner(shared_network)


@pytest.fixture
def two_daemons(tmp_path: Path, shared_network: ZeroTrustNetwork, signer: A2ASigner):
    """Spin up two daemons: laptop (sender), vps (receiver)."""
    shared_network.issue_identity("laptop-alice")
    shared_network.issue_identity("vps-bob")

    # Laptop side
    laptop_audit = AuditLog(tmp_path / "laptop-audit.jsonl")
    laptop_inbox = InboxStore(tmp_path / "laptop-inbox.sqlite")
    laptop_trust = TrustStore(tmp_path / "laptop-trust.json")
    laptop_resolver = IdentityResolver(tmp_path / "laptop-identity.json")

    # VPS side
    vps_audit = AuditLog(tmp_path / "vps-audit.jsonl")
    vps_inbox = InboxStore(tmp_path / "vps-inbox.sqlite")
    vps_trust = TrustStore(tmp_path / "vps-trust.json")
    vps_resolver = IdentityResolver(tmp_path / "vps-identity.json")

    laptop_port = _free_port()
    vps_port = _free_port()

    laptop_url = f"http://127.0.0.1:{laptop_port}/a2a"
    vps_url = f"http://127.0.0.1:{vps_port}/a2a"

    laptop_resolver.register("laptop-alice", laptop_url)
    laptop_resolver.register("vps-bob", vps_url)
    vps_resolver.register("laptop-alice", laptop_url)
    vps_resolver.register("vps-bob", vps_url)

    # Reputations
    laptop_trust.set_score("vps-bob", 0.9)
    vps_trust.set_score("laptop-alice", 0.9)

    laptop_daemon = ReceivingDaemon(
        receiver_id="laptop-alice",
        signer=signer,
        trust=laptop_trust,
        inbox=laptop_inbox,
        audit=laptop_audit,
    )
    vps_daemon = ReceivingDaemon(
        receiver_id="vps-bob",
        signer=signer,
        trust=vps_trust,
        inbox=vps_inbox,
        audit=vps_audit,
    )

    laptop_server = A2AServer(laptop_port, laptop_daemon.handle_request)
    vps_server = A2AServer(vps_port, vps_daemon.handle_request)
    laptop_server.start()
    vps_server.start()
    time.sleep(0.1)

    yield {
        "laptop": {
            "audit": laptop_audit,
            "inbox": laptop_inbox,
            "trust": laptop_trust,
            "resolver": laptop_resolver,
            "server": laptop_server,
            "daemon": laptop_daemon,
            "url": laptop_url,
        },
        "vps": {
            "audit": vps_audit,
            "inbox": vps_inbox,
            "trust": vps_trust,
            "resolver": vps_resolver,
            "server": vps_server,
            "daemon": vps_daemon,
            "url": vps_url,
        },
    }

    laptop_server.stop()
    vps_server.stop()


# ─── Test 1: happy path ──────────────────────────────────────────────────────


def test_1_happy_path_signature_reputation_inbox_accept_result(
    two_daemons, signer: A2ASigner, tmp_path: Path
) -> None:
    """End-to-end: send → verify → inbox → accept → result returns to sender."""
    laptop = two_daemons["laptop"]
    vps = two_daemons["vps"]

    code_file = tmp_path / "auth.rs"
    code_file.write_text("// auth module\nfn login() {}\n")

    result = send_task(
        SendOptions(
            sender_id="laptop-alice",
            target_id="vps-bob",
            task_text="review auth module",
            file_path=code_file,
        ),
        resolver=laptop["resolver"],
        trust=laptop["trust"],
        signer=signer,
        vault=VaultClient(),
        audit=laptop["audit"],
    )

    assert result.ok, result.reason
    assert result.task_id

    # Sender audit
    laptop_entries = laptop["audit"].read_all()
    assert any(e.action == "send_task" and e.task_id == result.task_id for e in laptop_entries)
    assert any(e.signature_hash for e in laptop_entries if e.action == "send_task")

    # Receiver state
    summaries = list_inbox(vps["inbox"])
    assert len(summaries) == 1
    assert summaries[0].task_id == result.task_id
    assert summaries[0].sender == "laptop-alice"
    assert summaries[0].status == "pending"
    assert "review auth" in summaries[0].preview

    # Receiver audit
    vps_entries = vps["audit"].read_all()
    assert any(e.action == "receive_task" for e in vps_entries)

    # Accept
    accept = accept_task(
        result.task_id,
        receiver_id="vps-bob",
        store=vps["inbox"],
        audit=vps["audit"],
        resolver=vps["resolver"],
        signer=signer,
    )
    assert accept.ok
    assert accept.result_sent

    # Result lands on laptop side
    time.sleep(0.2)
    laptop_entries2 = laptop["audit"].read_all()
    assert any(e.action == "receive_result" and e.task_id == result.task_id for e in laptop_entries2)


# ─── Test 2: low-reputation sender ───────────────────────────────────────────


def test_2_low_reputation_sender_requires_explicit_accept(
    two_daemons, signer: A2ASigner
) -> None:
    """Low-rep sender's task is queued but content redacted in list_inbox."""
    laptop = two_daemons["laptop"]
    vps = two_daemons["vps"]

    # Drop sender reputation on VPS side
    vps["trust"].set_score("laptop-alice", 0.1)

    result = send_task(
        SendOptions(
            sender_id="laptop-alice",
            target_id="vps-bob",
            task_text="harmless cleanup task",
        ),
        resolver=laptop["resolver"],
        trust=laptop["trust"],
        signer=signer,
        vault=VaultClient(),
        audit=laptop["audit"],
    )
    assert result.ok

    # On inbox list, content must be redacted while pending
    summaries = list_inbox(vps["inbox"])
    assert len(summaries) == 1
    assert summaries[0].status == "pending"
    assert "<redacted" in summaries[0].preview
    assert "harmless cleanup task" not in summaries[0].preview

    # After accept, content becomes visible
    accept_task(
        result.task_id,
        receiver_id="vps-bob",
        store=vps["inbox"],
        audit=vps["audit"],
        resolver=vps["resolver"],
        signer=signer,
    )
    summaries_after = list_inbox(vps["inbox"])
    assert summaries_after[0].status != "pending"


# ─── Test 3: credential-touching task — no raw secret on wire ────────────────


def test_3_credential_task_no_raw_secret_in_payload(
    two_daemons, signer: A2ASigner
) -> None:
    """Credential-touching task: raw secret never serialized; only proxy token is."""
    laptop = two_daemons["laptop"]

    raw_secret = "sk-ant-VERY-SECRET-DO-NOT-LEAK-aBcDeFgHiJkLmNoPq0123"
    vault = VaultClient()
    vault.store("anthropic-api", raw_secret)

    result = send_task(
        SendOptions(
            sender_id="laptop-alice",
            target_id="vps-bob",
            task_text="deploy production with anthropic key",
            confirm=True,  # auto-approve credential gate
            credential_service="anthropic-api",
        ),
        resolver=laptop["resolver"],
        trust=laptop["trust"],
        signer=signer,
        vault=vault,
        audit=laptop["audit"],
    )

    assert result.ok
    payload = result.serialized_payload.decode()

    # Assert raw secret NEVER appears in the serialized wire payload
    assert raw_secret not in payload
    assert "VERY-SECRET" not in payload

    # Assert proxy token IS in the payload
    assert "synapse+vault://proxy/" in payload
    assert "vaultProxy" in payload


# ─── Test 4: unreachable target — fail fast ──────────────────────────────────


def test_4_unreachable_target_fails_fast(tmp_path: Path, shared_network: ZeroTrustNetwork) -> None:
    """No queue; immediate clear error when target is unreachable."""
    shared_network.issue_identity("laptop-alice")

    resolver = IdentityResolver(tmp_path / "ident.json")
    # Register target at a never-listening port
    dead_port = _free_port()
    resolver.register("ghost-agent", f"http://127.0.0.1:{dead_port}/a2a")

    trust = TrustStore(tmp_path / "t.json")
    trust.set_score("ghost-agent", 0.9)
    audit = AuditLog(tmp_path / "a.jsonl")
    signer = A2ASigner(shared_network)

    start = time.time()
    result = send_task(
        SendOptions(
            sender_id="laptop-alice",
            target_id="ghost-agent",
            task_text="hello",
        ),
        resolver=resolver,
        trust=trust,
        signer=signer,
        vault=VaultClient(),
        audit=audit,
    )
    elapsed = time.time() - start

    assert not result.ok
    assert "unreachable" in result.reason.lower()
    # Fail fast: well under 5 seconds
    assert elapsed < 5.0

    # No queue created
    assert not (tmp_path / "queue.sqlite").exists()


# ─── Test 5: tampered/unsigned message rejected, audit logged, no crash ──────


def test_5_tampered_message_rejected_logged_no_crash(
    two_daemons, signer: A2ASigner, shared_network: ZeroTrustNetwork
) -> None:
    """Receiver rejects bad signatures + logs them, never crashes."""
    vps = two_daemons["vps"]

    import urllib.request

    # Forge an unsigned message
    forged = b'{"jsonrpc":"2.0","method":"message/send","params":{"task":{"id":"forged-1"}},"id":"x"}'

    req = urllib.request.Request(
        vps["url"],
        data=forged,
        headers={
            "Content-Type": "application/json",
            "X-A2A-Sender": "laptop-alice",
            "X-A2A-Signature": "0" * 64,  # wrong signature
        },
        method="POST",
    )
    import json as _json
    with urllib.request.urlopen(req, timeout=2) as resp:
        body = _json.loads(resp.read())
    assert "error" in body

    # Audit log has rejection
    entries = vps["audit"].read_all()
    assert any(e.action == "reject_unsigned" for e in entries)

    # Receiver still alive — send a legitimate task and confirm it works
    laptop = two_daemons["laptop"]
    result = send_task(
        SendOptions(
            sender_id="laptop-alice",
            target_id="vps-bob",
            task_text="post-tamper sanity",
        ),
        resolver=laptop["resolver"],
        trust=laptop["trust"],
        signer=signer,
        vault=VaultClient(),
        audit=laptop["audit"],
    )
    assert result.ok, f"receiver crashed after tampered message: {result.reason}"
