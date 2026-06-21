# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""CLI entry point — `synapse` command.

Wires the real ``commands/send_task.py`` and ``commands/inbox.py``
implementations to the argparse front end. State (identity registry,
trust scores, audit log, inbox queue) lives under
``$SYNAPSE_HOME`` (default ``~/.synapse``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from synapse.security.zero_trust import ZeroTrustNetwork

from .a2a_signer import A2ASigner
from .audit import AuditLog
from .commands.inbox import accept_task, list_inbox, reject_task
from .commands.send_task import SendOptions, send_task
from .identity_resolver import IdentityResolver
from .inbox_store import InboxStore
from .trust import DEFAULT_TRUST_THRESHOLD, TrustStore
from .vault_client import VaultClient


def _home() -> Path:
    raw = os.environ.get("SYNAPSE_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".synapse"


def _build_state(home: Path) -> tuple[
    IdentityResolver, TrustStore, A2ASigner, VaultClient, AuditLog, InboxStore
]:
    home.mkdir(parents=True, exist_ok=True)
    resolver = IdentityResolver(home / "identity.json")
    trust = TrustStore(home / "trust.json")
    signer = A2ASigner(ZeroTrustNetwork())
    vault = VaultClient()
    audit = AuditLog(home / "audit.jsonl")
    inbox = InboxStore(home / "inbox.db")
    return resolver, trust, signer, vault, audit, inbox


def _cmd_send(args: argparse.Namespace) -> int:
    home = _home()
    resolver, trust, signer, vault, audit, _ = _build_state(home)

    file_path: Path | None = Path(args.file).expanduser() if args.file else None
    opts = SendOptions(
        sender_id=args.sender,
        target_id=args.target,
        task_text=args.task,
        file_path=file_path,
        confirm=bool(args.confirm),
        trust_threshold=DEFAULT_TRUST_THRESHOLD,
        credential_service=args.credential_service or "",
    )

    def _ask(msg: str) -> bool:
        ans = input(f"{msg} [y/N] ").strip().lower()
        return ans in ("y", "yes")

    result = send_task(
        opts,
        resolver=resolver,
        trust=trust,
        signer=signer,
        vault=vault,
        audit=audit,
        confirm_fn=_ask,
    )
    print(json.dumps({
        "ok": result.ok,
        "task_id": result.task_id,
        "reason": result.reason,
        "signed_payload_bytes": len(result.serialized_payload),
        "response": result.response,
    }, indent=2, sort_keys=True))
    return 0 if result.ok else 2


def _cmd_inbox(args: argparse.Namespace) -> int:
    home = _home()
    resolver, _, signer, _, audit, inbox = _build_state(home)

    if args.subcmd == "list":
        rows = list_inbox(inbox)
        print(json.dumps([asdict(r) for r in rows], indent=2, sort_keys=True))
        return 0

    if args.subcmd == "accept":
        if not args.task_id:
            print("error: task_id required for accept", file=sys.stderr)
            return 2
        result = accept_task(
            args.task_id,
            receiver_id=args.receiver,
            store=inbox,
            audit=audit,
            resolver=resolver,
            signer=signer,
        )
        print(json.dumps({
            "ok": result.ok,
            "task_id": result.task_id,
            "result_sent": result.result_sent,
            "reason": result.reason,
        }, indent=2, sort_keys=True))
        return 0 if result.ok else 2

    if args.subcmd == "reject":
        if not args.task_id:
            print("error: task_id required for reject", file=sys.stderr)
            return 2
        result = reject_task(
            args.task_id,
            receiver_id=args.receiver,
            store=inbox,
            audit=audit,
            reason=args.reason or "",
        )
        print(json.dumps({
            "ok": result.ok,
            "task_id": result.task_id,
            "reason": result.reason,
        }, indent=2, sort_keys=True))
        return 0 if result.ok else 2

    return 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="synapse", description="Synapse CLI")
    subs = parser.add_subparsers(dest="cmd", required=True)

    send = subs.add_parser("send-task", help="Send an A2A task to another agent")
    send.add_argument("--from", dest="sender", required=True, help="sender agent id")
    send.add_argument("--to", dest="target", required=True, help="target agent id")
    send.add_argument("--task", required=True, help="task description text")
    send.add_argument("--file", dest="file", help="attach file as A2A artifact")
    send.add_argument("--confirm", action="store_true", help="auto-confirm prompts")
    send.add_argument(
        "--credential-service",
        dest="credential_service",
        default="",
        help="vault service to issue a credential proxy for",
    )
    send.set_defaults(handler=_cmd_send)

    inbox = subs.add_parser("inbox", help="List / accept / reject received tasks")
    inbox.add_argument(
        "subcmd", nargs="?", default="list", choices=["list", "accept", "reject"]
    )
    inbox.add_argument("task_id", nargs="?", help="task id for accept/reject")
    inbox.add_argument(
        "--as", dest="receiver", default="self",
        help="local agent id acting as the receiver",
    )
    inbox.add_argument("--reason", default="", help="reason text for reject")
    inbox.set_defaults(handler=_cmd_inbox)

    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
