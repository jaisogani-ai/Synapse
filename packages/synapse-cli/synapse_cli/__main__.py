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
from .blob import BlobCache
from .commands.inbox import accept_task, list_inbox, reject_task, review_task
from .commands.send_task import SendOptions, send_task
from .identity_resolver import IdentityResolver
from .inbox_store import InboxStore
from .outbox_store import OutboxStore
from .outbox_worker import OutboxWorker
from .presence import LocalPresence, VALID_STATUS, probe
from .trust import DEFAULT_TRUST_THRESHOLD, TrustStore
from .vault_client import VaultClient


def _home() -> Path:
    raw = os.environ.get("SYNAPSE_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".synapse"


def _build_state(home: Path) -> tuple[
    IdentityResolver, TrustStore, A2ASigner, VaultClient, AuditLog, InboxStore,
    OutboxStore, BlobCache,
]:
    home.mkdir(parents=True, exist_ok=True)
    resolver = IdentityResolver(home / "identity.json")
    trust = TrustStore(home / "trust.json")
    signer = A2ASigner(ZeroTrustNetwork())
    vault = VaultClient()
    audit = AuditLog(home / "audit.jsonl")
    inbox = InboxStore(home / "inbox.db")
    outbox = OutboxStore(home / "outbox.db")
    blob_cache = BlobCache(home / "blobs")
    return resolver, trust, signer, vault, audit, inbox, outbox, blob_cache


def _cmd_send(args: argparse.Namespace) -> int:
    home = _home()
    resolver, trust, signer, vault, audit, _, outbox, blob_cache = _build_state(home)

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

    blob_base_url = os.environ.get("SYNAPSE_BLOB_BASE_URL", "")
    result = send_task(
        opts,
        resolver=resolver,
        trust=trust,
        signer=signer,
        vault=vault,
        audit=audit,
        outbox=outbox,
        blob_cache=blob_cache,
        blob_base_url=blob_base_url,
        confirm_fn=_ask,
    )
    print(json.dumps({
        "ok": result.ok,
        "queued": result.queued,
        "task_id": result.task_id,
        "reason": result.reason,
        "signed_payload_bytes": len(result.serialized_payload),
        "response": result.response,
    }, indent=2, sort_keys=True))
    return 0 if result.ok else 2


def _cmd_presence(args: argparse.Namespace) -> int:
    home = _home()
    resolver, _, _, _, _, _, _, _ = _build_state(home)
    local = LocalPresence(home / "presence.json")

    if args.subcmd == "set":
        if args.status not in VALID_STATUS:
            print(
                f"error: status must be one of {sorted(VALID_STATUS)}",
                file=sys.stderr,
            )
            return 2
        local.set(args.status)
        print(json.dumps({"status": local.get()}, sort_keys=True))
        return 0

    if args.subcmd == "get":
        print(json.dumps({"status": local.get()}, sort_keys=True))
        return 0

    if args.subcmd == "list":
        # Probe every known agent in the identity registry.
        snaps = []
        for agent_id, endpoint in sorted(
            resolver._registry.items()  # noqa: SLF001 — intentional internal view
        ):
            snap = probe(agent_id, endpoint)
            snaps.append({
                "agent_id": snap.agent_id,
                "endpoint": snap.endpoint,
                "status": snap.status,
                "reachable": snap.reachable,
                "checked_at": snap.checked_at,
            })
        print(json.dumps(snaps, indent=2, sort_keys=True))
        return 0

    return 1


def _cmd_outbox(args: argparse.Namespace) -> int:
    home = _home()
    _, _, signer, _, audit, _, outbox, _ = _build_state(home)

    if args.subcmd == "list":
        states = (
            ("queued", "failed", "sent", "dead")
            if args.all
            else ("queued", "failed", "dead")
        )
        rows = outbox.list_by_state(states)
        out = [
            {
                "task_id": r.task_id,
                "target": r.target_id,
                "state": r.state,
                "attempts": r.attempts,
                "enqueued_at": r.enqueued_at,
                "next_retry_at": r.next_retry_at,
                "last_error": r.last_error,
            }
            for r in rows
        ]
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    if args.subcmd == "retry":
        if not args.task_id:
            print("error: task_id required for retry", file=sys.stderr)
            return 2
        ok = outbox.requeue(args.task_id)
        print(json.dumps({"ok": ok, "task_id": args.task_id}, sort_keys=True))
        return 0 if ok else 2

    if args.subcmd == "flush":
        worker = OutboxWorker(
            outbox, audit, network=signer._network  # noqa: SLF001
        )
        processed = worker.tick()
        print(json.dumps({"processed": processed}, sort_keys=True))
        return 0

    if args.subcmd == "purge":
        removed = outbox.purge_sent(older_than_seconds=args.older_than)
        print(json.dumps({"removed": removed}, sort_keys=True))
        return 0

    return 1


def _cmd_inbox(args: argparse.Namespace) -> int:
    home = _home()
    resolver, _, signer, _, audit, inbox, _, _ = _build_state(home)

    if args.subcmd == "list":
        rows = list_inbox(inbox)
        print(json.dumps([asdict(r) for r in rows], indent=2, sort_keys=True))
        return 0

    if args.subcmd == "review":
        if not args.task_id:
            print("error: task_id required for review", file=sys.stderr)
            return 2
        result = review_task(args.task_id, inbox)
        print(json.dumps({
            "ok": result.ok,
            "task_id": result.task_id,
            "sender": result.sender,
            "sender_score": result.sender_score,
            "status": result.status,
            "received_at": result.received_at,
            "text": result.text,
            "attachments": list(result.attachments),
            "reason": result.reason,
        }, indent=2, sort_keys=True))
        return 0 if result.ok else 2

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

    inbox = subs.add_parser("inbox", help="List / accept / reject / review received tasks")
    inbox.add_argument(
        "subcmd",
        nargs="?",
        default="list",
        choices=["list", "accept", "reject", "review"],
    )
    inbox.add_argument("task_id", nargs="?", help="task id for accept/reject/review")
    inbox.add_argument(
        "--as", dest="receiver", default="self",
        help="local agent id acting as the receiver",
    )
    inbox.add_argument("--reason", default="", help="reason text for reject")
    inbox.set_defaults(handler=_cmd_inbox)

    presence = subs.add_parser(
        "presence", help="Show / set local status (online|busy|offline) or probe peers"
    )
    presence.add_argument(
        "subcmd", nargs="?", default="get", choices=["get", "set", "list"]
    )
    presence.add_argument(
        "status", nargs="?", default="", help="online|busy|offline (for set)"
    )
    presence.set_defaults(handler=_cmd_presence)

    outbox = subs.add_parser(
        "outbox", help="List / retry / flush / purge the durable send queue"
    )
    outbox.add_argument(
        "subcmd",
        nargs="?",
        default="list",
        choices=["list", "retry", "flush", "purge"],
    )
    outbox.add_argument("task_id", nargs="?", help="task id for retry")
    outbox.add_argument(
        "--all", action="store_true", help="include sent rows in list output"
    )
    outbox.add_argument(
        "--older-than",
        dest="older_than",
        type=int,
        default=86400,
        help="purge sent rows older than N seconds (default 1 day)",
    )
    outbox.set_defaults(handler=_cmd_outbox)

    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
