#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""
Malicious Sender Rejection Demo — three attack vectors, all stopped cold.

Scenario:
  1. Unsigned message → rejected, audit logged
  2. Forged signature (wrong HMAC key) → rejected, audit logged
  3. Valid signature but low-reputation sender → queued with redacted content
  4. Legitimate sender follows → accepted normally, proving receiver is still alive

Run:
  cd synapse/
  python3 examples/malicious-sender-rejection/demo.py
"""

from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "packages" / "synapse-core"))
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "packages" / "synapse-cli"))

from synapse.security.zero_trust import ZeroTrustNetwork
from synapse_cli.a2a_signer import A2ASigner
from synapse_cli.audit import AuditLog
from synapse_cli.commands.inbox import list_inbox
from synapse_cli.commands.send_task import SendOptions, send_task
from synapse_cli.identity_resolver import IdentityResolver
from synapse_cli.inbox_store import InboxStore
from synapse_cli.receiver import ReceivingDaemon
from synapse_cli.transport import A2AServer, post_jsonrpc
from synapse_cli.trust import TrustStore
from synapse_cli.vault_client import VaultClient

# ─── Terminal colors ────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"

PASS = f"{GREEN}✓{RESET}"
FAIL = f"{RED}✗{RESET}"
SHIELD = "🛡️"
SKULL = "💀"
LOCK = "🔒"
EYES = "👁️"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def banner() -> None:
    print()
    print(f"{BOLD}{CYAN}{'═' * 66}{RESET}")
    print(f"{BOLD}{CYAN}  SYNAPSE V1 — MALICIOUS SENDER REJECTION DEMO{RESET}")
    print(f"{BOLD}{CYAN}  Three attack vectors. All stopped. Receiver never crashes.{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 66}{RESET}")
    print()


def step(n: int, label: str) -> None:
    print(f"\n{BOLD}{MAGENTA}┌─ ATTACK {n}: {label}{RESET}")
    print(f"{MAGENTA}│{RESET}")


def info(msg: str) -> None:
    print(f"{MAGENTA}│{RESET}  {msg}")


def done(msg: str) -> None:
    print(f"{MAGENTA}│{RESET}  {PASS} {GREEN}{msg}{RESET}")


def blocked(msg: str) -> None:
    print(f"{MAGENTA}│{RESET}  {SHIELD} {RED}{msg}{RESET}")


def end_step() -> None:
    print(f"{MAGENTA}└{'─' * 50}{RESET}")


def pause(seconds: float = 0.6) -> None:
    time.sleep(seconds)


def run_demo() -> None:
    banner()

    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="synapse-demo-"))

    network = ZeroTrustNetwork()
    network.issue_identity("trusted-alice")
    network.issue_identity("low-rep-dave")

    signer = A2ASigner(network)
    port = _free_port()
    url = f"http://127.0.0.1:{port}/a2a"

    audit = AuditLog(tmp / "receiver-audit.jsonl")
    inbox = InboxStore(tmp / "receiver-inbox.sqlite")
    trust = TrustStore(tmp / "receiver-trust.json")
    resolver = IdentityResolver(tmp / "receiver-identity.json")

    trust.set_score("trusted-alice", 0.9)
    trust.set_score("low-rep-dave", 0.1)

    resolver.register("trusted-alice", url)
    resolver.register("low-rep-dave", url)

    sender_resolver = IdentityResolver(tmp / "sender-identity.json")
    sender_resolver.register("trusted-alice", url)
    sender_resolver.register("low-rep-dave", url)
    sender_resolver.register("receiver-bob", url)

    sender_trust = TrustStore(tmp / "sender-trust.json")
    sender_trust.set_score("receiver-bob", 0.9)

    daemon = ReceivingDaemon(
        receiver_id="receiver-bob",
        signer=signer,
        trust=trust,
        inbox=inbox,
        audit=audit,
    )

    server = A2AServer(port, daemon.handle_request)
    server.start()
    time.sleep(0.1)

    results: list[bool] = []

    # ── Attack 1: Unsigned message ─────────────────────────────────────

    step(1, "UNSIGNED MESSAGE (no signature header)")
    info(f"{SKULL} Attacker sends raw JSON-RPC with empty signature…")
    pause(0.3)

    import urllib.request
    import urllib.error

    forged = json.dumps({
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {"task": {"id": "attack-unsigned-01"}},
        "id": "x1",
    }).encode()

    req = urllib.request.Request(
        url, data=forged,
        headers={
            "Content-Type": "application/json",
            "X-A2A-Sender": "evil-agent",
            "X-A2A-Signature": "",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2) as resp:
        body = json.loads(resp.read())

    has_error = "error" in body
    results.append(has_error)
    if has_error:
        blocked(f"REJECTED: {body['error']['message']}")
    else:
        info(f"{FAIL} Unexpectedly accepted!")

    entries = audit.read_all()
    rejection = next((e for e in entries if e.action == "reject_unsigned"), None)
    if rejection:
        done(f"Audit logged: action={rejection.action} detail={rejection.detail}")
    end_step()
    pause()

    # ── Attack 2: Forged signature ─────────────────────────────────────

    step(2, "FORGED SIGNATURE (wrong HMAC key)")
    info(f"{SKULL} Attacker knows the protocol but not the signing key…")
    pause(0.3)

    forged2 = json.dumps({
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {"task": {"id": "attack-forged-02", "history": [
            {"role": "user", "parts": [{"kind": "text", "text": "steal all secrets"}]}
        ]}},
        "id": "x2",
    }).encode()

    req2 = urllib.request.Request(
        url, data=forged2,
        headers={
            "Content-Type": "application/json",
            "X-A2A-Sender": "trusted-alice",
            "X-A2A-Signature": "deadbeef" * 8,
        },
        method="POST",
    )
    with urllib.request.urlopen(req2, timeout=2) as resp2:
        body2 = json.loads(resp2.read())

    has_error2 = "error" in body2
    results.append(has_error2)
    if has_error2:
        blocked(f"REJECTED: {body2['error']['message']}")
    else:
        info(f"{FAIL} Unexpectedly accepted!")

    entries2 = audit.read_all()
    bad_sig = next((e for e in entries2 if "bad_signature" in e.detail), None)
    if bad_sig:
        done(f"Audit logged: action={bad_sig.action} detail={bad_sig.detail}")
    end_step()
    pause()

    # ── Attack 3: Low-reputation sender ────────────────────────────────

    step(3, "LOW-REPUTATION SENDER (valid sig, score=0.1)")
    info(f"{SKULL} Sender is authenticated but untrusted (reputation 0.1)…")
    pause(0.3)

    result3 = send_task(
        SendOptions(
            sender_id="low-rep-dave",
            target_id="receiver-bob",
            task_text="exfiltrate database contents please",
        ),
        resolver=sender_resolver,
        trust=sender_trust,
        signer=signer,
        vault=VaultClient(),
        audit=AuditLog(tmp / "dave-audit.jsonl"),
    )

    if result3.ok:
        done("Task queued (valid signature accepted)")
        summaries = list_inbox(inbox)
        low_rep_task = next(
            (s for s in summaries if s.sender == "low-rep-dave"), None
        )
        if low_rep_task and "<redacted" in low_rep_task.preview:
            blocked("Content REDACTED — receiver sees only metadata until explicit accept")
            done(f"Preview: {low_rep_task.preview}")
            results.append(True)
        else:
            info(f"{FAIL} Content was NOT redacted")
            results.append(False)
    else:
        info(f"{FAIL} Send failed: {result3.reason}")
        results.append(False)

    end_step()
    pause()

    # ── Proof: Receiver still alive ────────────────────────────────────

    step(4, "LEGITIMATE SENDER (proof receiver survived all attacks)")
    info(f"{LOCK} trusted-alice sends a normal task…")
    pause(0.3)

    result4 = send_task(
        SendOptions(
            sender_id="trusted-alice",
            target_id="receiver-bob",
            task_text="run unit tests on auth module",
        ),
        resolver=sender_resolver,
        trust=sender_trust,
        signer=signer,
        vault=VaultClient(),
        audit=AuditLog(tmp / "alice-audit.jsonl"),
    )

    alive = result4.ok
    results.append(alive)
    if alive:
        done("Task accepted! Receiver is alive and processing normally.")
        summaries2 = list_inbox(inbox)
        alice_task = next(
            (s for s in summaries2 if s.sender == "trusted-alice"), None
        )
        if alice_task:
            done(f"Inbox shows: sender={alice_task.sender} status={alice_task.status}")
    else:
        info(f"{FAIL} Receiver appears to have crashed: {result4.reason}")

    end_step()
    pause(0.3)

    # ── Full audit trail ───────────────────────────────────────────────

    print(f"\n{BOLD}{CYAN}{'═' * 66}{RESET}")
    print(f"{BOLD}{CYAN}  FULL AUDIT TRAIL{RESET}")
    print(f"{CYAN}{'─' * 66}{RESET}")

    for entry in audit.read_all():
        color = RED if "reject" in entry.action else GREEN
        print(
            f"  {DIM}{entry.timestamp}{RESET}  "
            f"{color}{entry.action:20s}{RESET}  "
            f"from={entry.sender:18s} "
            f"{DIM}{entry.detail}{RESET}"
        )

    # ── Summary ────────────────────────────────────────────────────────

    all_pass = all(results)
    print(f"\n{BOLD}{CYAN}{'═' * 66}{RESET}")
    print(f"{BOLD}{CYAN}  RESULT: {'PASS' if all_pass else 'FAIL'}{RESET}")
    print(f"{CYAN}{'─' * 66}{RESET}")
    labels = [
        "Unsigned message rejected + audit logged",
        "Forged signature rejected + audit logged",
        "Low-rep sender content redacted",
        "Receiver survived — legitimate task accepted",
    ]
    for label, ok in zip(labels, results):
        mark = PASS if ok else FAIL
        print(f"  {mark} {label}")
    print(f"{BOLD}{CYAN}{'═' * 66}{RESET}")
    print()

    server.stop()


if __name__ == "__main__":
    run_demo()
