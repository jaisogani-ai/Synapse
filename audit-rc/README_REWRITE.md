# README_REWRITE

**Note to reader:** This is a drop-in replacement for `README.md`. It describes
the repository that actually exists today (per `REPOSITORY_INVENTORY.md` and
`ARCHITECTURE_REALITY.md`), in the tone the brief asked for: Stripe / Tailscale /
Vercel / Rust Foundation — concise, technical, confident, no buzzwords.

Apply by `cp audit-rc/README_REWRITE.md README.md` (after the launch blockers in
`RELEASE_SCORE.md` are addressed).

The remainder of this file is the proposed README body, verbatim.

---

<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# 🔐 Synapse

> Your AI agents can already talk to each other.
> They have no idea who they're talking to.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Daemon](https://img.shields.io/badge/daemon-Rust-orange.svg)](daemon/)
[![SDK](https://img.shields.io/badge/SDK-Python%203.11%2B-green.svg)](packages/synapse-core/)
[![Vault](https://img.shields.io/badge/vault-Node%2020%2B-yellow.svg)](packages/synapse-vault-mcp/)

Synapse is a trust layer for agent-to-agent (A2A) communication. It signs every
message with the sender's cryptographic identity, scores senders by their
observed behaviour, and hands over secrets through scoped, time-limited proxies
so the agent never sees the raw key.

It does **not** replace A2A. It does **not** orchestrate agents. It plugs in
underneath the agents you already run.

## The problem

The A2A specification gives two agents a shared envelope: `Task`, `Message`,
`Part`, `Artifact`. It says nothing about *who* sent the envelope, *whether*
they should be trusted, or *what they're allowed to do once you accept it*.

In practice every A2A integration today re-implements the same three things,
badly:

1. Some kind of bearer token or pre-shared key, sometimes rotated.
2. A list of "agents we trust", maintained by hand.
3. Raw API keys passed through the message body to whichever agent is asked
   to deploy.

Synapse replaces all three with primitives.

## What Synapse provides

| Pillar | What it does | Where it lives |
|---|---|---|
| **Identity** | Per-agent HMAC-SHA256 signing keys; short-lived HS256 JWTs (`sub`, `iat`, `exp`, `caps`); every request verified before any side effect. | [`packages/synapse-core`](packages/synapse-core) (Python) |
| **Trust** | Confidence-weighted reputation scores in `0..=100`, recorded outcome-by-outcome and queryable as `should_trust(agent, domain)`. SQLite-backed. | [`daemon/`](daemon) (Rust) + [`packages/synapse-core`](packages/synapse-core) (Python score store) |
| **Vault** | AES-256-GCM secret store. Agents receive a `synapse+vault://proxy/<token>` URL with a TTL — never the raw secret. | [`packages/synapse-vault-mcp`](packages/synapse-vault-mcp) (TypeScript) |
| **Signed A2A** | Wrap an A2A `message/send` or `tasks/result` payload in an HMAC-signed envelope; receiver verifies signature, freshness, and reputation before queueing. | [`packages/synapse-cli`](packages/synapse-cli) (Python) |

The pieces compose. A signed A2A `message/send` reaches the receiver, the
receiver looks up the sender's reputation in the trust store, and if the task
requires a credential the agent gets a vault proxy — not the secret itself.

## A complete handoff in 12 lines

```python
from synapse.security.zero_trust import ZeroTrustNetwork
from synapse_cli.a2a_signer import A2ASigner
from synapse_cli.transport import post_jsonrpc

network = ZeroTrustNetwork()
network.issue_identity("ops-bot")                 # mint signing key
signer  = A2ASigner(network)

payload = b'{"jsonrpc":"2.0","method":"message/send","id":"1","params":{...}}'
signed  = signer.sign("ops-bot", payload)         # HMAC over (payload || ts)

post_jsonrpc(                                     # plain A2A wire format
    url="http://vps.local:8721/a2a",
    payload_bytes=signed.payload,
    sender_id=signed.sender_id,
    signature_hex=signed.signature_hex,
    timestamp=signed.timestamp,
)
```

The receiver discards anything without a valid signature, anything older than
five minutes, or anything from an agent below the reputation threshold —
*before* it parses the task.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Your tools  (Claude Code · Cursor · Codex · VS Code · etc.)     │
└───────────────┬──────────────────────────────────────────────────┘
                │
                │  Python SDK: sign + verify, capability gate
                ▼
┌──────────────────────────────────────────────────────────────────┐
│  packages/synapse-core      packages/synapse-cli                 │
│  · zero_trust  (JWT/HMAC)   · a2a_signer / receiver / transport  │
│  · capabilities             · send_task  / inbox / audit         │
└───────────────┬──────────────────────────────────────────────────┘
                │
                │  Synapse Protocol v1.0 over a Unix socket
                ▼
┌──────────────────────────────────────────────────────────────────┐
│  daemon/  (Rust, async tokio)                                    │
│  · trust::reputation   — SQLite-backed scoring                   │
│  · protocol            — Synapse Protocol v1.0                   │
│  · ipc                 — Unix-socket server                      │
└──────────────────────────────────────────────────────────────────┘
```

The Rust daemon is intentionally small. It owns the reputation store and the
Synapse Protocol; everything else — A2A signing, the secret vault, capability
enforcement at the call site — runs in the satellite packages.

## What's in this repository

```
synapse/
├── daemon/                          # Rust daemon — trust store, protocol, IPC
├── packages/
│   ├── synapse-core/                # Python SDK: identity, capabilities, scanners
│   ├── synapse-cli/                 # Python: A2A send/receive, inbox, audit
│   ├── synapse-vault-mcp/           # TypeScript: AES-256-GCM vault as an MCP server
│   └── adapters/                    # Thin adapters labelling tool integrations
├── examples/
│   ├── vps-handoff-no-raw-keys/     # VPS deploy without ever sending a raw key
│   ├── malicious-sender-rejection/  # Three attack vectors, three clean rejects
│   └── cross-device-task-delegation/# Two-terminal A2A delegation, trust-gated
├── docs/                            # Architecture · Trust model · Protocol · Roadmap
└── spinout/                         # v0 modules with standalone value, out of v1 scope
```

## Demos

```bash
# Codex on a VPS deploys without ever holding the raw key
python3 examples/vps-handoff-no-raw-keys/demo.py

# Three attempts to spoof a trusted sender, all rejected at the gate
python3 examples/malicious-sender-rejection/demo.py

# A2A task delegation between two devices (two terminals)
python3 examples/cross-device-task-delegation/run_vps.py     # terminal 1
python3 examples/cross-device-task-delegation/run_laptop.py  # terminal 2
```

## Build & test

```bash
# Rust daemon
cargo build
cargo test

# Python SDK + adapters + CLI
pip install -e ".[dev]"
pytest

# TypeScript vault MCP
cd packages/synapse-vault-mcp && npm install && npm test
```

## What Synapse is not

- **Not an agent framework.** Synapse provides identity and trust; the agents
  themselves run inside Claude Code, Cursor, Codex, or whatever you use.
- **Not a replacement for A2A.** Synapse signs and verifies A2A messages
  byte-for-byte. The wire format is the A2A wire format.
- **Not a model router.** Routing/cost utilities are spun out under
  [`spinout/`](spinout/) and may move to their own repos.

## Status

This repository is a release candidate. The Rust daemon's reputation store, the
Python identity / capabilities / signing primitives, the TypeScript vault MCP,
and the three end-to-end demos are all real and tested. Production hardening
(token refresh, on-disk daemon persistence, signed audit log, tamper-evident
trust store) is tracked in [`docs/ROADMAP.md`](docs/ROADMAP.md) Phase E. Items
deferred from the security review are listed in
[`LAUNCH_BLOCKERS.md`](LAUNCH_BLOCKERS.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — what the daemon does, what the SDK does
- [Trust Model](docs/TRUST_MODEL.md) — the three gates, the threat model
- [Protocol](docs/PROTOCOL.md) — Synapse Protocol v1.0 wire format
- [Roadmap](docs/ROADMAP.md) — done, in flight, planned
- [Inspirations](docs/INSPIRATIONS.md) — what shaped the design

## License

Apache 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Free for personal and commercial use. Attribution required per the NOTICE file.

— Built in Jaipur by [Jai Sogani](https://github.com/jaisogani-ai).
