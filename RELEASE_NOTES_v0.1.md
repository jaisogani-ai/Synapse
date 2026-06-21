<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Synapse v0.1.0-alpha — Release Notes

**Date:** 2026-06-22
**License:** Apache 2.0

Synapse is an open-source trust layer for agent-to-agent (A2A) communication.
It provides cryptographic identity, reputation scoring, scoped credential
proxies, and per-method capability enforcement — bolted onto the standard A2A
protocol you already use.

This is an **alpha** release. The primitives are implemented, tested, and
demonstrated. Expect rough edges. Known gaps are documented in
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

---

## What's in v0.1.0-alpha

| Pillar | Summary |
|---|---|
| **Identity** | Per-agent HMAC-SHA256 signing keys. Short-lived HS256 JWTs with `sub`, `iat`, `exp`, and `caps` claims. Every request verified before any side effect. |
| **Vault** | AES-256-GCM secret store (TypeScript/Node). Agents receive scoped, time-limited proxy URLs — never the raw secret. Raw key exposure is audited and asserted zero in the demo. |
| **Trust** | Confidence-weighted reputation scoring. Low-reputation senders have content redacted in the inbox. Outcome-weighted history produces a 0–100 score. |
| **Capability gate** | Every A2A method requires a specific capability. The sender's JWT must grant it, and the `sub` must match the HMAC sender. Wired on both the Python receiver and the Rust IPC dispatcher. |
| **A2A transport** | Standard JSON-RPC over HTTP. HMAC-signed envelopes. Spec-compliant `FilePart` with `uri` for large files. Synapse does **not** replace A2A. |
| **Durable outbox** | Offline target → SQLite queue → background worker retries with exponential backoff → DLQ after 6 attempts. |
| **Chunked file transfer** | Files > 256 KiB served via content-addressed blob endpoint with HTTP `Range` resume and sha256 end-to-end verification. |
| **Presence** | `online` / `busy` / `offline`. Simple HTTP GET. No CRDT, no gossip. |
| **Inbox + review** | SQLite-backed received-task queue. Operator can review content before accepting or rejecting. |
| **Audit log** | Append-only JSONL of every send, receive, accept, reject, and capability denial. |
| **5 adapters** | Claude Code, Cursor, Codex, VS Code, Antigravity — each subclassing `BaseAdapter`. 42 adapter tests. |
| **CLI** | `send-task`, `inbox list/review/accept/reject`, `outbox list/flush`, `presence list/set`. |

## Tests

| Suite | Count |
|---|---|
| `cargo test` (Rust daemon) | 39 / 39 |
| `pytest` (Python SDK + CLI + adapters) | 79 / 79 |
| `npm test` (vault MCP) | 10 / 10 |
| **Total** | **128 / 128** |

## Demos

All three demos run end-to-end against real code paths — no in-process
simulation of the vault, signing, or capability gate.

| Demo | What it proves | Status |
|---|---|---|
| [vps-handoff-no-raw-keys](examples/vps-handoff-no-raw-keys/) | Real AES-256-GCM vault, scoped proxy, zero raw-key exposure | PASS |
| [cross-device-task-delegation](examples/cross-device-task-delegation/) | Two-terminal walkthrough — laptop sends, VPS receives, result returns | green |
| [malicious-sender-rejection](examples/malicious-sender-rejection/) | Forged signature, missing capability, low-rep redaction — all rejected | PASS |

## Stack

| Component | Language | LOC (approx) |
|---|---|---|
| Rust daemon | Rust 1.80+ | ~1,500 |
| Python SDK + CLI + adapters | Python 3.11+ | ~3,500 |
| Vault MCP | TypeScript / Node 20+ | ~400 |
| **Total** | | **~5,400** |

## Known limitations

This is not an exhaustive list — see [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md)
for the full table. Headlines:

- **No federation, relay, or discovery.** You configure each peer's URL manually.
- **Rust `TrustStore` is in-memory.** Restart loses recorded outcomes.
- **No end-to-end payload encryption.** Sign + gate, yes; encrypt, no. Use HTTPS or a tunnel.
- ~~Audit log is not tamper-evident.~~ **Hash-chained as of v0.1.0-alpha** — `synapse audit verify` walks the chain.
- **`vault_client.py` is plaintext in-memory.** Use the vault MCP for persisted secrets.

## What's next

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full follow-up list:

- v0.2: SQLite-backed Rust trust store, WAL inbox, per-sender rate limits, endpoint pinning
- Beyond v0.2 (open questions, not committed): Asymmetric tokens (Ed25519), optional E2E encryption, Rust-native identity + vault

## Non-goals

Synapse is deliberately not: a new wire protocol, a federation framework, a
memory layer, an agent runtime, an orchestration framework, a hosted SaaS, or
an "agent OS."

## Install

```bash
git clone https://github.com/jaisogani-ai/synapse.git synapse
cd synapse
npm install && npm --workspace @synapse/secret-vault-mcp run build
pip install -e ".[dev]"
cargo build --release
cargo test && pytest && npm test   # 128 / 128
```

## Links

| Resource | Where |
|---|---|
| Architecture | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Trust model | [`docs/TRUST_MODEL.md`](docs/TRUST_MODEL.md) |
| Security review | [`SECURITY_REVIEW.md`](SECURITY_REVIEW.md) |
| Vulnerability reporting | [`SECURITY.md`](SECURITY.md) |
| Roadmap | [`docs/ROADMAP.md`](docs/ROADMAP.md) |
| Bug report | [`BUG_REPORT.md`](BUG_REPORT.md) |

---

<sub>Built by Jai Sogani. The repo is small on purpose.</sub>
