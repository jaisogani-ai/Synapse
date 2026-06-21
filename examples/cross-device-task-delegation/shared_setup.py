# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Shared-state helper for the cross-device demo.

Both terminal scripts (`run_laptop.py` and `run_vps.py`) call into here so
they share identity files, trust scores, and a single zero-trust network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from synapse.security.zero_trust import ZeroTrustNetwork
from synapse_cli.audit import AuditLog
from synapse_cli.identity_resolver import IdentityResolver
from synapse_cli.inbox_store import InboxStore
from synapse_cli.trust import TrustStore

DEMO_ROOT = Path(__file__).parent
STATE_DIR = DEMO_ROOT / ".demo-state"

LAPTOP_PORT = 8102
VPS_PORT = 8101

LAPTOP_URL = f"http://127.0.0.1:{LAPTOP_PORT}/a2a"
VPS_URL = f"http://127.0.0.1:{VPS_PORT}/a2a"

# Demo uses a deterministic shared key so both processes verify each other.
SHARED_SECRET = b"\xa1" * 32


def ensure_dirs() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def build_shared_state(state_dir: Path) -> dict[str, Any]:
    network = ZeroTrustNetwork()
    # Inject deterministic identities so both demos verify each other's sigs
    network._secrets["laptop-alice"] = SHARED_SECRET  # noqa: SLF001 — demo only
    network._secrets["vps-bob"] = SHARED_SECRET  # noqa: SLF001 — demo only

    laptop_resolver = IdentityResolver(state_dir / "laptop-identity.json")
    laptop_resolver.register("laptop-alice", LAPTOP_URL)
    laptop_resolver.register("vps-bob", VPS_URL)

    vps_resolver = IdentityResolver(state_dir / "vps-identity.json")
    vps_resolver.register("laptop-alice", LAPTOP_URL)
    vps_resolver.register("vps-bob", VPS_URL)

    laptop_trust = TrustStore(state_dir / "laptop-trust.json")
    laptop_trust.set_score("vps-bob", 0.9)

    vps_trust = TrustStore(state_dir / "vps-trust.json")
    vps_trust.set_score("laptop-alice", 0.9)

    return {
        "network": network,
        "laptop_resolver": laptop_resolver,
        "vps_resolver": vps_resolver,
        "laptop_trust": laptop_trust,
        "vps_trust": vps_trust,
        "laptop_inbox": InboxStore(state_dir / "laptop-inbox.sqlite"),
        "vps_inbox": InboxStore(state_dir / "vps-inbox.sqlite"),
        "laptop_audit": AuditLog(state_dir / "laptop-audit.jsonl"),
        "vps_audit": AuditLog(state_dir / "vps-audit.jsonl"),
    }
