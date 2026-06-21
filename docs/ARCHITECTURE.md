<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Synapse Architecture

> v1 release-candidate — daemon, SDK, vault MCP, CLI.

## Overview

Synapse is structured as a **privileged daemon** (Rust) talking to its local
satellites (CLI, adapters, vault MCP) over a Unix domain socket using an
**internal IPC protocol** for identity, vault, and trust queries.

Cross-agent communication is a separate concern: tasks delegated between
agents use the **standard A2A protocol**
([a2aproject.org](https://a2aproject.org)) — JSON-RPC over HTTP with
HMAC-signed envelopes — implemented in
`packages/synapse-cli/synapse_cli/a2a.py`. Synapse signs and verifies A2A
messages; it does **not** reinvent the A2A wire format.

> Synapse's daemon uses an internal IPC protocol for identity/vault/trust
> operations. Cross-agent task delegation uses the standard A2A protocol
> ([a2aproject.org](https://a2aproject.org)), implemented in
> `packages/synapse-cli/synapse_cli/a2a.py` — not reinvented.

```
   CLI / adapters / MCPs  ──(internal IPC over Unix socket)──▶  DAEMON
                                                                  │
                            ┌────────────────────────────────────┤
                            │ Trust store (reputation scoring)   │
                            │ Daemon IPC v1.0 codec              │
                            │ IPC server (tokio async)           │
                            │ Capability enforcement (P1 wiring) │
                            └────────────────────────────────────┘

   agent ───(standard A2A JSON-RPC over HTTP)───▶ agent
        ▲                                            ▲
        └── signed by synapse_cli/a2a_signer.py ─────┘
            verified by synapse_cli/receiver.py
```

## The Four Pillars

### Identity
Cryptographic agent/device/account identity. Every agent receives a JWT
issued by the daemon. Every request is signed with HMAC-SHA256. No agent
is implicitly trusted.

**Implementation:** `packages/synapse-core/synapse/security/zero_trust.py`

### Vault
Agents never receive raw API keys. They request a scoped, time-limited
credential proxy; only the daemon resolves a proxy back to the real secret
at the network layer. Secrets are encrypted at rest with AES-256-GCM.
Every access is recorded in an append-only audit log.

**Implementation:** `packages/synapse-vault-mcp/src/vault.ts`

### Trust
Reputation scoring tracks the trustworthiness of every agent, MCP, and
decision over time. Confidence-weighted outcome history produces a 0–100
score. Supply-chain scanning validates MCP servers and packages via OSV.dev
and entropy heuristics.

**Implementation:** `daemon/src/trust/reputation.rs`,
`packages/synapse-core/synapse/security/supply_chain.py`,
`packages/synapse-core/synapse/security/capabilities.py`

### A2A Integration
Cross-agent task delegation uses the **standard A2A protocol**
([a2aproject.org](https://a2aproject.org)) — JSON-RPC over HTTP with
HMAC-signed envelopes. Synapse signs outbound A2A messages, verifies inbound
ones, and gates them through the three Trust Model gates. Synapse does **not**
replace or fork A2A.

The Rust daemon's `daemon/src/protocol/` module is **not** A2A — it is the
internal IPC protocol the daemon speaks with its own local CLI/adapter
clients for identity, vault, and trust queries. Do not confuse the two.

**Implementation:**
- A2A wire format and signer: `packages/synapse-cli/synapse_cli/a2a.py`,
  `packages/synapse-cli/synapse_cli/a2a_signer.py`
- A2A receiver: `packages/synapse-cli/synapse_cli/receiver.py`
- Daemon internal IPC (NOT A2A): `daemon/src/protocol/`, `daemon/src/ipc/`

## Daemon modules

| Module                    | Responsibility                                    |
|---------------------------|---------------------------------------------------|
| `main.rs`                 | Entry point; boots tracing, trust store, IPC      |
| `trust/reputation.rs`     | In-memory reputation scoring (SQLite-backed persistence on roadmap) |
| `protocol/mod.rs`         | **Internal** daemon IPC v1.0 message types + JSON codec (NOT A2A) — carries `caps: Vec<String>` per request |
| `ipc/mod.rs`              | Unix-socket server (tokio async); enforces capability per TrustOp (v1.0.1) |
| `security/capability.rs`  | `is_granted` + capability vocabulary; consulted by the IPC dispatcher (v1.0.1) |

## CLI / SDK modules (Python)

| Module | Responsibility |
|---|---|
| `synapse_cli/__main__.py` | CLI entry — `send-task`, `inbox`, `outbox`, `presence` |
| `synapse_cli/a2a.py` | A2A spec primitives (Task, Message, Part, FilePart with `uri`) |
| `synapse_cli/a2a_signer.py` | HMAC-SHA256 sign / verify over `payload \| timestamp` |
| `synapse_cli/transport.py` | HTTP JSON-RPC + A2AServer (`/a2a`, `/blob/<sha>`, `/presence`) |
| `synapse_cli/identity_resolver.py` | agent_id → endpoint URL registry |
| `synapse_cli/trust.py` | Authoritative Python trust store (JSON, v1) |
| `synapse_cli/inbox_store.py` | SQLite inbox (pending / accepted / rejected / completed) |
| `synapse_cli/outbox_store.py` | SQLite durable send queue (WAL); exponential backoff |
| `synapse_cli/outbox_worker.py` | Background worker draining the outbox; re-issues JWT per delivery |
| `synapse_cli/receiver.py` | `ReceivingDaemon` — Gate 1/2/3 enforcement on every inbound RPC |
| `synapse_cli/audit.py` | Append-only JSONL audit log |
| `synapse_cli/blob.py` | Content-addressed blob cache + chunked HTTP fetch with `Range` |
| `synapse_cli/presence.py` | online / busy / offline; LocalPresence + probe |
| `synapse_cli/vault_client.py` | In-process vault facade for sender-side proxy issuance |
| `synapse_cli/commands/send_task.py` | end-to-end send flow (resolve → presence → reputation → vault → sign → outbox/post → audit) |
| `synapse_cli/commands/inbox.py` | list / review / accept / reject + tasks/result return |

## SDK module (synapse-core)

| Module | Responsibility |
|---|---|
| `synapse.security.zero_trust` | `ZeroTrustNetwork` — identity, JWT, HMAC, `verify_request` |
| `synapse.security.capabilities` | `Capability`, `CapabilitySet`, vocabulary, `DEFAULT_A2A_CAPABILITIES` |
| `synapse.security.secret_detector` | 140+ leak patterns + entropy fallback |
| `synapse.security.supply_chain` | OSV.dev + Shannon entropy for MCP/package vetting |

## Vault MCP (Node)

| Module | Responsibility |
|---|---|
| `vault.ts` | `SecretVault` AES-256-GCM core + proxy issuance + redaction + tamper detection |
| `bridge.ts` | stdin/stdout JSON bridge so non-Node callers (e.g. the marquee demo) drive the real vault |
| `server.ts`, `index.ts` | MCP-style entry points |

## Authoritative stores (v1)

Two trust and identity stores currently exist (Rust SQLite-style + Python
JSON). For v1 the **Python stores under
`packages/synapse-core/synapse/security/` are authoritative**: they back
the CLI and have the broader test coverage. The Rust trust store is a
stub for the future Rust-native rewrite. Do not assume they are
synchronized.

## Threading model

- The IPC server is async (tokio); each connection is handled on a task.
- The trust store uses **interior mutability** (`Mutex`) so a single
  `Arc<TrustStore>` can be shared across connection tasks safely.
- The Rust trust store is **in-memory in v1**; restart loses recorded
  outcomes. SQLite-backed persistence is on the P1 roadmap (see below).
  When persistence lands, SQLite connections will be wrapped in a `Mutex`
  and long-term move to `spawn_blocking`.

## Roadmap

See [ROADMAP.md](ROADMAP.md). Notable P1 follow-ups visible from this
document:

- Wire `security/capability.rs` into the IPC dispatcher.
- Persist the Rust `TrustStore` to SQLite (currently in-memory).
- Reconcile the Rust and Python trust/identity stores into a single
  authoritative path, or move the canonical stores fully into Rust.
