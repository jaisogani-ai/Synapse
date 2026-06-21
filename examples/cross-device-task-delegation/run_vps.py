#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Run the VPS-side A2A receiver for the cross-device task delegation demo.

This script:
  - Boots a daemon on 127.0.0.1:8101
  - Loads the shared identity & trust files (so laptop & vps know each other)
  - Polls the inbox and prompts you to accept/reject each task
  - Sends results back to the sender via tasks/result
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "packages" / "synapse-core"))
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "packages" / "synapse-cli"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared_setup import build_shared_state, ensure_dirs  # noqa: E402

from synapse_cli.a2a_signer import A2ASigner  # noqa: E402
from synapse_cli.commands.inbox import accept_task, reject_task  # noqa: E402
from synapse_cli.receiver import ReceivingDaemon  # noqa: E402
from synapse_cli.transport import A2AServer  # noqa: E402

VPS_PORT = 8101

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def main() -> int:
    state = build_shared_state(ensure_dirs())
    network = state["network"]
    signer = A2ASigner(network)

    daemon = ReceivingDaemon(
        receiver_id="vps-bob",
        signer=signer,
        trust=state["vps_trust"],
        inbox=state["vps_inbox"],
        audit=state["vps_audit"],
    )

    server = A2AServer(VPS_PORT, daemon.handle_request)
    server.start()

    print(f"{BOLD}{CYAN}╔════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║  VPS DAEMON  vps-bob                       ║{RESET}")
    print(f"{BOLD}{CYAN}║  Listening on http://127.0.0.1:{VPS_PORT}/a2a  ║{RESET}")
    print(f"{BOLD}{CYAN}╚════════════════════════════════════════════╝{RESET}\n")
    print(f"{DIM}Waiting for incoming A2A tasks…{RESET}\n")

    seen: set[str] = set()
    try:
        while True:
            for row in state["vps_inbox"].list_all():
                if row.task_id in seen:
                    continue
                if row.status != "pending":
                    seen.add(row.task_id)
                    continue
                seen.add(row.task_id)
                print(f"{BOLD}{GREEN}📬  Task received from {row.sender}{RESET}")
                print(f"    {DIM}id:{RESET} {row.task_id}")
                print(f"    {DIM}signature:{RESET} {row.signature[:32]}… {GREEN}✓{RESET}")
                print(f"    {DIM}reputation:{RESET} {row.sender_score:.2f} {GREEN}✓{RESET}")
                ans = input(f"\n  Accept? [y/N] ").strip().lower()
                if ans == "y":
                    result = accept_task(
                        row.task_id,
                        receiver_id="vps-bob",
                        store=state["vps_inbox"],
                        audit=state["vps_audit"],
                        resolver=state["vps_resolver"],
                        signer=signer,
                    )
                    if result.ok and result.result_sent:
                        print(f"  {GREEN}✓ accepted — result sent back to {row.sender}{RESET}\n")
                    else:
                        print(f"  {YELLOW}⚠ {result.reason}{RESET}\n")
                else:
                    reject_task(
                        row.task_id,
                        receiver_id="vps-bob",
                        store=state["vps_inbox"],
                        audit=state["vps_audit"],
                        reason="user declined",
                    )
                    print(f"  {RED}✗ rejected{RESET}\n")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print(f"\n{DIM}Shutting down VPS daemon…{RESET}")
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
