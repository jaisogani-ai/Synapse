#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Run the laptop-side sender for the cross-device task delegation demo.

Sends "review auth module" + an attached file to vps-bob.
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
from synapse_cli.commands.send_task import SendOptions, send_task  # noqa: E402
from synapse_cli.receiver import ReceivingDaemon  # noqa: E402
from synapse_cli.transport import A2AServer  # noqa: E402
from synapse_cli.vault_client import VaultClient  # noqa: E402

LAPTOP_PORT = 8102

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def main() -> int:
    state = build_shared_state(ensure_dirs())
    network = state["network"]
    signer = A2ASigner(network)

    # Start laptop's own receiver so the VPS can return results
    daemon = ReceivingDaemon(
        receiver_id="laptop-alice",
        signer=signer,
        trust=state["laptop_trust"],
        inbox=state["laptop_inbox"],
        audit=state["laptop_audit"],
    )
    server = A2AServer(LAPTOP_PORT, daemon.handle_request)
    server.start()

    print(f"{BOLD}{CYAN}╔════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║  LAPTOP  laptop-alice                      ║{RESET}")
    print(f"{BOLD}{CYAN}║  Sending A2A task to vps-bob               ║{RESET}")
    print(f"{BOLD}{CYAN}╚════════════════════════════════════════════╝{RESET}\n")

    # Create the demo file
    demo_file = Path(__file__).parent / "auth_module.py"
    if not demo_file.exists():
        demo_file.write_text("""# auth module — sample file shipped via A2A artifact
def authenticate(user, password):
    return user is not None and password is not None
""")

    print(f"{DIM}→ Resolving vps-bob…{RESET}")
    print(f"{DIM}→ Presence check…{RESET}")
    print(f"{DIM}→ Reputation gate…{RESET}")
    print(f"{DIM}→ Building A2A Task + signing payload…{RESET}\n")

    result = send_task(
        SendOptions(
            sender_id="laptop-alice",
            target_id="vps-bob",
            task_text="review auth module",
            file_path=demo_file,
        ),
        resolver=state["laptop_resolver"],
        trust=state["laptop_trust"],
        signer=signer,
        vault=VaultClient(),
        audit=state["laptop_audit"],
    )

    if not result.ok:
        print(f"{YELLOW}✗ Send failed: {result.reason}{RESET}")
        server.stop()
        return 1

    print(f"{GREEN}✓ Task sent.{RESET}")
    print(f"  {DIM}task_id:{RESET} {result.task_id}")
    print(f"  {DIM}payload size:{RESET} {len(result.serialized_payload)} bytes\n")
    print(f"{DIM}← Waiting for result from VPS…{RESET}\n")

    # Wait up to ~30s for result
    laptop_inbox = state["laptop_inbox"]
    for _ in range(60):
        audit_entries = state["laptop_audit"].read_all()
        result_entry = next(
            (e for e in audit_entries if e.action == "receive_result" and e.task_id == result.task_id),
            None,
        )
        if result_entry is not None:
            print(f"{BOLD}{GREEN}← Result received:{RESET} {result_entry.detail}")
            break
        time.sleep(0.5)
    else:
        print(f"{YELLOW}⚠ Timed out waiting for result{RESET}")

    print(f"\n{DIM}Done. Press Ctrl+C to exit.{RESET}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
