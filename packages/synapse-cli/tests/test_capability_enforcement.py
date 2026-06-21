# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Receiver-side capability enforcement (Trust Model Gate 3).

These tests drive ``ReceivingDaemon.handle_request`` directly so they
exercise the capability gate without depending on the HTTP server.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from synapse.security.capabilities import DEFAULT_A2A_CAPABILITIES
from synapse.security.zero_trust import ZeroTrustNetwork
from synapse_cli.a2a import (
    JsonRpcRequest,
    METHOD_MESSAGE_SEND,
    METHOD_TASKS_GET,
    METHOD_TASKS_RESULT,
    Message,
    Task,
    TaskStatus,
    TextPart,
    new_context_id,
    new_task_id,
)
from synapse_cli.a2a_signer import A2ASigner
from synapse_cli.audit import AuditLog
from synapse_cli.inbox_store import InboxStore
from synapse_cli.receiver import METHOD_REQUIRED_CAPABILITY, ReceivingDaemon
from synapse_cli.trust import TrustStore


@pytest.fixture()
def state(tmp_path: Path):
    network = ZeroTrustNetwork()
    network.issue_identity("alice")
    network.issue_identity("bob")
    signer = A2ASigner(network)
    trust = TrustStore(tmp_path / "trust.json")
    trust.set_score("alice", 0.9)
    inbox = InboxStore(tmp_path / "inbox.db")
    audit = AuditLog(tmp_path / "audit.jsonl")
    daemon = ReceivingDaemon(
        receiver_id="bob",
        signer=signer,
        trust=trust,
        inbox=inbox,
        audit=audit,
    )
    return {
        "network": network,
        "signer": signer,
        "trust": trust,
        "inbox": inbox,
        "audit": audit,
        "daemon": daemon,
    }


def _signed_send_payload(network: ZeroTrustNetwork, sender_id: str = "alice"):
    task = Task(
        id=new_task_id(),
        context_id=new_context_id(),
        status=TaskStatus(state="submitted", timestamp=""),
        history=(Message(role="user", parts=(TextPart(text="ping"),)),),
    )
    rpc = JsonRpcRequest(
        method=METHOD_MESSAGE_SEND, params={"task": task.to_dict()}
    )
    payload = rpc.to_json().encode()
    ts = str(int(time.time()))
    sig = network.sign_payload(sender_id, payload + b"|" + ts.encode())
    return payload, sig, task.id, ts


def test_required_capability_map_covers_a2a_methods() -> None:
    """Every method the receiver dispatches must have a required cap."""
    assert METHOD_REQUIRED_CAPABILITY[METHOD_MESSAGE_SEND] == "a2a.send_task"
    assert METHOD_REQUIRED_CAPABILITY[METHOD_TASKS_RESULT] == "a2a.send_result"
    assert METHOD_REQUIRED_CAPABILITY[METHOD_TASKS_GET] == "a2a.read_status"


def test_request_without_token_is_denied(state) -> None:
    payload, sig, _, ts = _signed_send_payload(state["network"])
    resp = state["daemon"].handle_request(
        payload, "alice", sig, timestamp=ts, token=""
    )
    assert resp["error"]["message"].startswith("capability denied:")
    assert "missing X-A2A-Token" in resp["error"]["message"]
    actions = [e.action for e in state["audit"].read_all()]
    assert "reject_capability" in actions


def test_request_with_insufficient_capability_is_denied(state) -> None:
    network = state["network"]
    # Alice's token has trust.read but NOT a2a.send_task — message/send must reject.
    token = network.issue_token("alice", capabilities=["trust.read"])
    payload, sig, _, ts = _signed_send_payload(network)
    resp = state["daemon"].handle_request(
        payload, "alice", sig, timestamp=ts, token=token
    )
    assert "capability denied" in resp["error"]["message"]
    assert "not granted" in resp["error"]["message"]


def test_request_with_token_subject_mismatch_is_denied(state) -> None:
    network = state["network"]
    # Token signed for bob, request claims sender=alice — must reject.
    bob_token = network.issue_token(
        "bob", capabilities=list(DEFAULT_A2A_CAPABILITIES)
    )
    payload, sig, _, ts = _signed_send_payload(network, sender_id="alice")
    resp = state["daemon"].handle_request(
        payload, "alice", sig, timestamp=ts, token=bob_token
    )
    assert "capability denied" in resp["error"]["message"]
    assert "subject" in resp["error"]["message"]


def test_request_with_correct_token_is_accepted(state) -> None:
    network = state["network"]
    token = network.issue_token(
        "alice", capabilities=list(DEFAULT_A2A_CAPABILITIES)
    )
    payload, sig, task_id, ts = _signed_send_payload(network)
    resp = state["daemon"].handle_request(
        payload, "alice", sig, timestamp=ts, token=token
    )
    # message/send returns a result with taskId; no error key.
    assert "error" not in resp or resp.get("error") is None
    assert resp["result"]["taskId"] == task_id


def test_wildcard_token_grants_all_a2a_methods(state) -> None:
    network = state["network"]
    token = network.issue_token("alice", capabilities=["*"])
    payload, sig, task_id, ts = _signed_send_payload(network)
    resp = state["daemon"].handle_request(
        payload, "alice", sig, timestamp=ts, token=token
    )
    assert resp["result"]["taskId"] == task_id


def test_enforcement_can_be_disabled_for_legacy_tests(state, tmp_path) -> None:
    network = state["network"]
    daemon = ReceivingDaemon(
        receiver_id="bob",
        signer=state["signer"],
        trust=state["trust"],
        inbox=InboxStore(tmp_path / "legacy_inbox.db"),
        audit=AuditLog(tmp_path / "legacy_audit.jsonl"),
        enforce_capabilities=False,
    )
    payload, sig, task_id, ts = _signed_send_payload(network)
    resp = daemon.handle_request(
        payload, "alice", sig, timestamp=ts, token=""
    )
    assert resp["result"]["taskId"] == task_id
