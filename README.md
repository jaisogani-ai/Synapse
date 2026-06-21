<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Synapse

> **Identity, trust, reputation, and secure secret handoff for AI agents.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Daemon](https://img.shields.io/badge/daemon-Rust-orange.svg)](daemon/)
[![SDK](https://img.shields.io/badge/SDK-Python%203.11%2B-green.svg)](packages/synapse-core/)

Synapse gives AI agents cryptographic identity, capability-based trust,
reputation scoring, and scoped credential proxies — so agents can prove who
they are, what they're allowed to do, and whether they should be trusted.

![Synapse demo](assets/demo.gif)

> **Status:** v1 release candidate — Rust daemon (trust store + IPC),
> Python SDK, TypeScript AES-256-GCM vault MCP, CLI with A2A delegation,
> 5 tool adapters, 3 launch demos, full documentation.
>
> Identity, vault, and trust logic currently lives in the Python SDK at
> `packages/synapse-core/synapse/security/`. The Rust daemon is the
> trust/IPC/audit layer; native Rust identity/vault/a2a-signer modules
> are P1 follow-ups (see [ROADMAP.md](docs/ROADMAP.md)).

## The Four Pillars

| Pillar | What it does | Where it lives |
|--------|-------------|----------------|
| **Identity** | Cryptographic agent/device/account identity, JWT issuance, HMAC request signing | `packages/synapse-core/synapse/security/zero_trust.py` |
| **Vault** | Scoped, time-limited credential proxies; AES-256-GCM at rest; append-only audit trail | `packages/synapse-vault-mcp/src/vault.ts` |
| **Trust** | Reputation scoring, outcome tracking, capability verification, agent verification | `daemon/src/trust/reputation.rs`, `packages/synapse-core/synapse/security/` |
| **A2A Integration** | Sends and receives standard A2A tasks (a2aproject.org) with HMAC-signed JSON-RPC | `packages/synapse-cli/synapse_cli/a2a.py` |

## Architecture

```
┌──────────────────────────────────────────┐
│            SYNAPSE DAEMON (Rust)          │
│  • Trust store (reputation scoring)      │
│  • Internal IPC over Unix socket         │
│    (daemon ↔ local CLI / adapters)       │
│  • Capability-based policy enforcement   │
└──────────────────────────────────────────┘
        ▲
        │ identity / vault / trust queries
        │
┌──────────────────────────────────────────┐
│   CLI + adapters + vault MCP              │
│  • Cross-agent task delegation uses the  │
│    standard A2A protocol                 │
│    (packages/synapse-cli/synapse_cli/    │
│     a2a.py)                              │
└──────────────────────────────────────────┘
```

> Synapse's daemon uses an internal IPC protocol for identity/vault/trust
> operations. Cross-agent task delegation uses the standard A2A protocol
> ([a2aproject.org](https://a2aproject.org)), implemented in
> `packages/synapse-cli/synapse_cli/a2a.py` — not reinvented.

## Repository layout

```
synapse/
├── daemon/              # Rust daemon (trust store + IPC + audit transport)
│   └── src/
│       ├── trust/       # Reputation store
│       ├── protocol/    # Internal daemon ↔ client IPC v1.0 (NOT A2A)
│       ├── ipc/         # Unix-socket server
│       └── security/    # Capability enforcement (code-complete; wiring P1)
├── packages/
│   ├── synapse-core/    # Python SDK (zero-trust, capabilities, secret detector, supply chain)
│   ├── synapse-vault-mcp/   # AES-256-GCM secret vault (MCP server)
│   ├── synapse-cli/         # CLI tool (send-task, inbox, accept/reject, audit)
│   └── adapters/            # Claude Code, Cursor, Codex, VS Code, Antigravity
├── tests/               # Cross-language unit tests (72 tests)
├── examples/
│   ├── vps-handoff-no-raw-keys/       # Demo 1: VPS deploy, zero raw credentials
│   ├── malicious-sender-rejection/    # Demo 2: Three attack vectors, all stopped
│   └── cross-device-task-delegation/  # Demo 3: Trust-gated A2A delegation
├── spinout/             # Modules with standalone value, out of scope for v1
└── docs/                # Architecture, protocol, trust model, roadmap
```

## Demos

```bash
# VPS deploy — agent never sees raw API key
python3 examples/vps-handoff-no-raw-keys/demo.py

# Malicious sender rejection — three attacks, all stopped
python3 examples/malicious-sender-rejection/demo.py

# Cross-device task delegation (two terminals)
python3 examples/cross-device-task-delegation/run_vps.py     # terminal 1
python3 examples/cross-device-task-delegation/run_laptop.py  # terminal 2
```

## Build & test

```bash
# Rust daemon
cargo build
cargo test

# Python SDK + adapters + CLI (72 tests)
pip install -e ".[dev]"
pytest
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — daemon structure, threading, module map
- [Trust Model](docs/TRUST_MODEL.md) — three gates, reputation, threat model
- [Protocol](docs/PROTOCOL.md) — Synapse Protocol v1.0 wire format
- [Roadmap](docs/ROADMAP.md) — completed phases and planned work
- [Inspirations](docs/INSPIRATIONS.md) — design influences and non-goals

## License

Apache 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Free for personal and commercial use. Attribution required per NOTICE file.

— Built by Jai Sogani
