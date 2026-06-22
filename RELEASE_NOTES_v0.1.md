<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Synapse v0.1.0-alpha — Release Notes

**Date:** 2026-06-22
**License:** Apache 2.0
**Status:** Alpha — first public release

Synapse is an open-source **trust layer for agent-to-agent (A2A) communication**. It provides cryptographic identity, reputation scoring, scoped credential proxies, per-method capability enforcement, hash-chained audit, opt-in mTLS, and opt-in end-to-end encryption — bolted onto the standard A2A protocol you already use.

This is an **alpha** release. The primitives are implemented, tested, and demonstrated. Expect rough edges. Known gaps are documented openly in [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

---

## What's in v0.1.0-alpha

| Pillar | Summary |
|---|---|
| **Identity** | Per-agent HMAC-SHA256 signing keys. Short-lived HS256 JWTs with `sub`, `iat`, `exp`, and `caps` claims. Every request verified before any side effect. |
| **Device identity (DID-style)** | Stable `did:synapse:<agent_id>[#<device_id>]` identifier format. |
| **Vault** | AES-256-GCM secret store (TypeScript/Node). Agents receive scoped, time-limited proxy URLs — never the raw secret. Raw key exposure is audited and asserted zero in the demo. |
| **Trust + reputation** | Confidence-weighted scoring. Low-reputation senders have content redacted in the inbox until explicit accept. |
| **Capability gate** | Every A2A method requires a specific capability. The sender's JWT must grant it, and the `sub` must match the HMAC sender. Wired on both the Python receiver and the Rust IPC dispatcher. |
| **A2A transport** | Standard JSON-RPC over HTTP. HMAC-signed envelopes. Spec-compliant `FilePart` with `uri` for large files. Synapse does **not** replace A2A. |
| **Hash-chained audit log** | Append-only JSONL with `prev_hash` + `entry_hash` per row. `synapse audit verify` detects modified, deleted, or forged entries at the exact index. 8 tampering tests. |
| **Durable outbox** | Offline target → SQLite WAL queue → background worker with exponential backoff (5 s → 6 h) → DLQ after 6 attempts. |
| **Chunked file transfer** | Files > 256 KiB served via content-addressed blob endpoint with HTTP `Range` resume and sha256 end-to-end verification. `MAX_BLOB_BYTES = 2 GiB`. |
| **Presence** | `online` / `busy` / `offline` over `GET /presence`. No CRDT, no gossip. |
| **Inbox + review** | SQLite-backed received-task queue. Operator can review content before accepting or rejecting. |
| **Opt-in mTLS** | Self-signed mutual TLS. `pip install synapse[mtls]` + `synapse identity gen-cert <agent>` + `SYNAPSE_MTLS=1` enables it. HTTP remains the default. 10 tests cover the real TLS handshake. |
| **End-to-end encryption** | X25519 + HKDF-SHA256 + AES-256-GCM sealed envelopes. `synapse identity gen-keypair <agent>` + `synapse send-task --encrypt`. Only the recipient's private key decrypts; forward-secret per message; receiver fails closed without the key. 17 tests. |
| **Patch review workflow** | Reviewing agents return unified diffs; senders apply with strict context validation or loop comment → revise → resubmit. `synapse patch make / summarize / apply`. 12 tests. |
| **5 platform adapters** | Claude Code, Cursor, Codex, VS Code, Antigravity — each subclassing `BaseAdapter`. 42 adapter tests. |
| **CLI** | `send-task`, `inbox list/review/accept/reject`, `outbox list/flush/retry/purge`, `presence get/set/list`, `audit verify/tail/review`, `identity gen-cert/gen-keypair/list-certs/list-keys`, `patch make/summarize/apply`, `quarantine list/add/release`. |
| **Quarantine + threat response** | Per-agent failure counter, auto-block after 5 consecutive Gate-1 failures, manual release. |
| **Rate anomaly detection** | Per-sender Z-score over a 60-second sliding window of 1-second buckets. |
| **Access review** | `synapse audit review` summarizes the hash-chained log by sender/receiver/action with optional time window. |
| **Continuous Verifier** | Labelled three-gate orchestrator; tests pin gate order (signature → reputation → capability) and short-circuit semantics. |
| **Secret detector** | 140+ provider patterns + Shannon-entropy fallback; redaction. |
| **Supply-chain check** | OSV.dev CVE lookup + entropy heuristics for MCP / package vetting. |

---

## Tests

| Suite | Count |
|---|---|
| `cargo test` (Rust daemon) | 39 / 39 |
| `pytest` (Python SDK + CLI + adapters) | 145 / 145 |
| `npm test` (vault MCP) | 10 / 10 |
| **Total** | **194 / 194** ✅ |

---

## Demos

All three demos run end-to-end against real code paths — no in-process simulation of the vault, signing, or capability gate.

| Demo | What it proves | Status |
|---|---|---|
| [vps-handoff-no-raw-keys](examples/vps-handoff-no-raw-keys/) | Real AES-256-GCM vault, scoped proxy, zero raw-key exposure | PASS |
| [cross-device-task-delegation](examples/cross-device-task-delegation/) | Two-terminal walkthrough — laptop sends, VPS receives, patch review loop, result returns | green |
| [malicious-sender-rejection](examples/malicious-sender-rejection/) | Forged signature, missing capability, low-rep redaction — all rejected | PASS |

---

## Stack

| Component | Language | LOC (approx) |
|---|---|---|
| Rust daemon | Rust 1.80+ | ~1,500 |
| Python SDK + CLI + adapters | Python 3.11+ | ~3,500 |
| Vault MCP | TypeScript / Node 20+ | ~400 |
| **Total** | | **~5,400** |

---

## Known limitations

This is the honest headline list — see [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) for the full table with impact, mitigation, and plan.

- **No federation, relay, or discovery service.** You configure each peer's URL manually in `identity.json`. **By design.**
- **Rust `TrustStore` is in-memory.** Daemon restart loses recorded outcomes. The Python store is v0.1-authoritative.
- **mTLS and E2E encryption are opt-in.** The default A2A path is HMAC-signed over HTTP. Turn on mTLS / E2E / a tunnel for confidentiality on hostile networks.
- **mTLS is self-signed** with manual cert distribution — no CA / revocation infrastructure yet.
- **`vault_client.py` is plaintext in-memory.** Use the vault MCP for persisted secrets.
- **HMAC (HS256), not asymmetric (Ed25519).** The receiver must hold the sender's secret to verify.
- **No CI workflow yet.** Run `cargo test && pytest && npm test` locally before pushing. Planned for v0.2.
- **Tested on macOS (Darwin 25.5).** Linux should work; Windows is untested.

---

## What's next

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full follow-up list:

**v0.2 (planned, contained changes):**

- Persistent Rust trust store (SQLite-backed)
- Endpoint hash pinning on `identity.json`
- Per-sender token-bucket rate limit on the receiver
- Encrypt-at-rest for `vault_client.py`
- Inbox SQLite WAL + busy timeout
- JWT `cnf` (confirmation) claim binding token to specific request
- GitHub Actions CI + CycloneDX SBOM on release
- Release automation

**Beyond v0.2 (open questions, not committed):**

- Asymmetric (Ed25519) tokens instead of HS256
- Code-gen capability vocabulary from one source of truth
- Rust-native identity + vault, replacing the Python + Node implementations
- CA-backed mTLS

---

## Non-goals

Synapse is deliberately **not**:

- A new wire protocol (A2A is the wire format)
- A federation framework
- A memory layer (use Mem0 / Supermemory / Graphiti)
- An agent runtime or orchestration system
- A multi-tenant SaaS
- An "agent OS"
- A marketplace

Synapse stays small on purpose.

---

## Install

```bash
git clone https://github.com/jaisogani-ai/Synapse.git synapse
cd synapse

# JS / vault MCP
npm install
npm --workspace @synapse/secret-vault-mcp run build

# Python SDK + CLI + adapters  (add [mtls] for mutual TLS + E2E encryption)
pip install -e ".[dev]"

# Rust daemon
cargo build --release

# Sanity check — should be 194/194
cargo test
pytest -q
npm test
```

---

## Links

| Resource | Where |
|---|---|
| README | [`README.md`](README.md) |
| Architecture | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Trust model | [`docs/TRUST_MODEL.md`](docs/TRUST_MODEL.md) |
| Daemon IPC protocol | [`docs/PROTOCOL.md`](docs/PROTOCOL.md) |
| Security review (threat model) | [`SECURITY_REVIEW.md`](SECURITY_REVIEW.md) |
| Vulnerability reporting | [`SECURITY.md`](SECURITY.md) |
| Roadmap | [`docs/ROADMAP.md`](docs/ROADMAP.md) |
| Known limitations | [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) |
| Changelog | [`CHANGELOG.md`](CHANGELOG.md) |

---

<sub>Built by Jai Sogani · The repo is small on purpose · ⭐ <a href="https://github.com/jaisogani-ai/Synapse/stargazers">Star Synapse</a> if it's useful</sub>
