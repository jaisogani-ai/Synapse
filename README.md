<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

<div align="center">

<!-- Hero image — save your concept diagram as assets/hero.png to render -->
<img src="assets/hero.png" alt="Synapse — Trusted A2A for Claude Code, Cursor, Codex, Antigravity, VS Code" width="900" onerror="this.style.display='none'">

# 🔐 Synapse

### Your AI agents can already talk to each other.<br>They have no idea who they're talking to.

Trusted A2A for **Claude Code, Cursor, Codex, Antigravity, VS Code** — and anything else that speaks the A2A spec.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](packages/synapse-core/)
[![Rust](https://img.shields.io/badge/Rust-1.80%2B-CE412B.svg?logo=rust&logoColor=white)](daemon/)
[![TypeScript](https://img.shields.io/badge/TypeScript-Node%2020%2B-3178C6.svg?logo=typescript&logoColor=white)](packages/synapse-vault-mcp/)
[![Tests](https://img.shields.io/badge/tests-155%2F155-brightgreen.svg)](#tests)
[![A2A](https://img.shields.io/badge/A2A-spec--compliant-7C3AED.svg)](https://a2aproject.org)

</div>

> **⚠️ Synapse v0.1.0-alpha.** Early open-source release. The trust primitives
> (identity, reputation, vault, capability gate, hash-chained audit) are
> implemented and tested. This is alpha — there is no SLA and several
> follow-ups are listed openly in [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).
> Break things, open issues.

---

## Demo

Watch Synapse securely hand off credentials between devices without exposing secrets.

<div align="center">

<video src="assets/synapse-demo.mp4" controls muted loop autoplay playsinline width="900">
  Your browser does not support the HTML video tag.
  <a href="assets/synapse-demo.mp4">Download the 45-second demo</a> or
  <a href="assets/demo.gif">view the animated GIF fallback</a>.
</video>

<sub>Full 45 seconds · 1280×720 · audio included · ~19 MB.<br>If the video tag doesn't render in your viewer, the GIF below plays the same content.</sub>

</div>

![Synapse demo fallback](assets/demo.gif)

---

## Problem

When Claude Code on your laptop sends a task to Codex on your VPS today, **anything in between can:**

- forge the request — there's no identity check
- read the credential — it's in the payload
- replay the message — there's no expiry
- pretend to be the target — there's no verification
- escalate privilege — there's no capability check
- silently rewrite the audit log — there's no tamper evidence

A2A defines the message envelope. It doesn't tell you who's on either end of it, what they're allowed to do, whether you should trust them, how to hand them a secret without leaking it, or how to prove later that nothing was tampered with.

**Synapse is the trust layer.** Identity. Reputation. Capabilities. Vault. Hash-chained audit. All bolted onto the A2A protocol you already use.

---

## How it works

```
Without Synapse:           With Synapse:

Claude Code on laptop      Claude Code on laptop
       │                          │
       │  unsigned, unaudited     │  HMAC-signed envelope + capability JWT
       │  raw API key in body     │  vault proxy URL (raw secret never leaves)
       │  no capability check     │  caps verified per RPC method
       │  no replay window        │  ±300 s timestamp drift
       │  audit can be rewritten  │  hash-chained — tamper detectable
       ▼                          ▼
Codex on VPS               Codex on VPS
   "Trust me, I'm           "Identity verified.
    Alice."                  Reputation 0.91.
                             Capability granted.
                             Audit row #4327 chained."
```

A2A is the wire format. Synapse is the trust layer.

---

## Architecture diagram

<!-- Save your detailed concept diagram as assets/architecture.png to render here -->
<img src="assets/architecture.png" alt="Synapse architecture overview" width="900" onerror="this.style.display='none'">

```
┌──────────────────────────────────────────────────────────┐
│            SYNAPSE DAEMON  (Rust)                          │
│  • Trust store — reputation scoring per agent + domain    │
│  • Internal IPC over Unix socket                          │
│  • Capability enforcement on each TrustOp                 │
└──────────────────────────────────────────────────────────┘
        ▲                                            ▲
        │ identity / vault / trust queries           │
┌──────────────────────┐                ┌────────────────────────┐
│ packages/synapse-cli │                │ packages/synapse-      │
│  • send-task         │                │  vault-mcp (Node)      │
│  • inbox / outbox    │                │  AES-256-GCM vault     │
│  • presence          │                │  Scoped proxy tokens   │
│  • audit verify      │                │  Append-only audit     │
└──────────┬───────────┘                └────────────────────────┘
           │
           │   standard A2A protocol  (JSON-RPC over HTTP,
           │   signed with HMAC-SHA256, capability JWT in header)
           ▼
       Other agent on another device
```

The 6 source-true Mermaid flow diagrams (high-level, identity, vault, A2A task, capability, trust) live in [`docs/diagrams/`](docs/diagrams/).

> **Diagram disclosure.** Visual concept diagrams (`hero.png`, `architecture.png`) above show the v0.1.0-alpha trust layer. Below is the exact mapping from diagram label → what ships today.
>
> ✅ **Implemented in v0.1.0-alpha:** Identity (per-agent HMAC + HS256 JWT) · Trust & Reputation (confidence-weighted) · Vault & Secrets (AES-256-GCM + scoped proxies) · A2A Messaging (spec-compliant) · Audit & Logging (**hash-chained, forensically verifiable**) · Capability Enforcement (per RPC method + per Rust IPC TrustOp) · Secret Detector (140+ patterns) · Risk Scoring (reputation = risk score) · Policy Enforcement (capability gate) · Anomaly Detection (per-sender rate Z-score) · Threat Response (auto-block after N consecutive Gate-1 failures) · Quarantine & Isolation (`synapse quarantine`) · Access Review (`synapse audit review`) · Continuous Verification (every message walks all three gates) · Device Identity in `did:synapse:<agent_id>` format.
>
> ❌ **Not yet implemented:** Mutual TLS (use HTTPS/Tailscale at the transport layer) · full W3C DID-method registry · end-to-end payload encryption · Behaviour Analysis as an ML model (we ship reputation, which is statistical, not learned). All listed in [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).
>
> Phrases the diagrams use that this README does **not**: "Enterprise Grade", "Production Ready". Synapse is v0.1.0-alpha — those phrases would be incorrect.

---

## Features

Everything below is wired up, tested, and demonstrated. No placeholders.

| Pillar | What it does | Where it lives |
|---|---|---|
| **Identity** | HMAC-SHA256 per-agent secrets, HS256 JWTs with `sub` / `iat` / `exp` / `caps` claims, 15-min TTL | [`packages/synapse-core/synapse/security/zero_trust.py`](packages/synapse-core/synapse/security/zero_trust.py) |
| **Vault** | AES-256-GCM at rest, scoped time-limited proxy URLs, raw secret never on the wire, append-only audit | [`packages/synapse-vault-mcp/src/vault.ts`](packages/synapse-vault-mcp/src/vault.ts) |
| **Trust + reputation** | Confidence-weighted scoring per agent + domain; redacts content from low-rep senders until explicit accept | [`packages/synapse-cli/synapse_cli/trust.py`](packages/synapse-cli/synapse_cli/trust.py), [`daemon/src/trust/`](daemon/src/trust/) |
| **Capability enforcement** | Per RPC method on the A2A receiver, per TrustOp on the Rust IPC dispatcher; sender's JWT must grant the required cap and `sub` must match HMAC sender | [`receiver.py`](packages/synapse-cli/synapse_cli/receiver.py), [`daemon/src/ipc/mod.rs`](daemon/src/ipc/mod.rs) |
| **A2A integration** | Standard JSON-RPC over HTTP, spec-compliant `FilePart` with `uri` for large files | [`packages/synapse-cli/synapse_cli/a2a.py`](packages/synapse-cli/synapse_cli/a2a.py) |
| **Durable outbox** | SQLite queue with exponential backoff (5s→6h) and DLQ after `MAX_ATTEMPTS = 6` | [`outbox_store.py`](packages/synapse-cli/synapse_cli/outbox_store.py), [`outbox_worker.py`](packages/synapse-cli/synapse_cli/outbox_worker.py) |
| **Chunked file transfer** | Files > 256 KiB served from content-addressed blob endpoint with HTTP `Range` resume and SHA-256 end-to-end verify | [`blob.py`](packages/synapse-cli/synapse_cli/blob.py) |
| **Presence** | `online` / `busy` / `offline` over `GET /presence`. Simple HTTP. No CRDT, no gossip. | [`presence.py`](packages/synapse-cli/synapse_cli/presence.py) |
| **Inbox + review** | SQLite-backed received-task queue; `synapse inbox review <id>` shows full content before accept/reject | [`inbox_store.py`](packages/synapse-cli/synapse_cli/inbox_store.py), [`commands/inbox.py`](packages/synapse-cli/synapse_cli/commands/inbox.py) |
| **Hash-chained audit** | Append-only JSONL with `prev_hash` + `entry_hash` per row. `synapse audit verify` detects modifications, deletions, forged inserts. | [`audit.py`](packages/synapse-cli/synapse_cli/audit.py) |
| **Static secret detection** | 140+ vendor patterns + entropy heuristic for pre-commit / pre-send scanning | [`secret_detector.py`](packages/synapse-core/synapse/security/secret_detector.py) |
| **Quarantine + threat response** | Per-agent counter on Gate-1 failures; auto-quarantine after 5 consecutive; manual list/add/release via `synapse quarantine` | [`quarantine.py`](packages/synapse-core/synapse/security/quarantine.py), [`threat_response.py`](packages/synapse-core/synapse/security/threat_response.py) |
| **Rate anomaly detection** | Per-sender Z-score over a 60 s sliding window of 1 s buckets — bursts at ≥ 3σ above the rolling mean are flagged | [`anomaly.py`](packages/synapse-core/synapse/security/anomaly.py) |
| **Access review** | `synapse audit review` summarizes the hash-chained log by sender/receiver/action inside an optional time window | [`access_review.py`](packages/synapse-core/synapse/security/access_review.py) |
| **Device identity (DID)** | Stable `did:synapse:<agent_id>[#<device_id>]` identifier format. Not full W3C DID method registry. | [`device_identity.py`](packages/synapse-core/synapse/security/device_identity.py) |
| **Continuous Verifier** | The labelled three-gate orchestrator (quarantine → signature → reputation → capability). Tests pin gate order and short-circuit. | [`continuous_verifier.py`](packages/synapse-core/synapse/security/continuous_verifier.py) |
| **5 platform adapters** | Claude Code, Cursor, Codex, VS Code, Antigravity — each ~30 LOC on `BaseAdapter`; 42 tests pass | [`packages/adapters/`](packages/adapters/) |

### Tests

| Suite | Result | Command |
|---|---|---|
| `cargo test` | **39 / 39** ✅ | `cargo test` |
| `pytest` | **106 / 106** ✅ | `PYTHONPATH=… python3.11 -m pytest tests packages/adapters packages/synapse-cli/tests -q` |
| `npm test` (vault MCP) | **10 / 10** ✅ | `(cd packages/synapse-vault-mcp && npm test)` |
| **Total** | **155 / 155** | |

Plus the live `vps-handoff-no-raw-keys` demo: **RESULT: PASS** (real AES-256-GCM vault driven via the Node bridge, asserts zero raw-key audit exposure).

---

## Security model

Three gates on every inbound A2A message. Failure at any gate stops the message and writes a hash-chained audit row.

```
   inbound A2A message
        │
        ▼
  ┌─────────────┐    Gate 1: HMAC-SHA256 signature valid?
  │  SIGNATURE  │ →  Timestamp inside ±300 s drift?
  └──────┬──────┘     reject_unsigned / reject_bad_signature
         ▼
  ┌─────────────┐    Gate 2: sender reputation ≥ threshold (default 0.5)?
  │  REPUTATION │ →  Low-rep content redacted in inbox list until accept.
  └──────┬──────┘
         ▼
  ┌─────────────┐    Gate 3: sender's JWT grants the required capability
  │  CAPABILITY │ →  for this RPC method? sub == HMAC sender?
  └──────┬──────┘     reject_capability
         ▼
     dispatch → row written to hash-chained audit log
```

Threat model, attack classes (spoofing, replay, secret leakage, capability escalation, impersonation, audit tampering, DoS), fixed issues, and assumptions live in [`SECURITY_REVIEW.md`](SECURITY_REVIEW.md).

Vulnerability reporting policy: [`SECURITY.md`](SECURITY.md).

---

## Examples

Live in [`examples/`](examples/). Each runs end-to-end against the real code paths — no in-process simulation of the vault, signing, or capability gate.

### Demo 1 — VPS deploy with no raw credentials

Codex on a VPS deploys an app using an Anthropic API key. The key never leaves the laptop's vault; the VPS sees only a 300-second proxy URL. Drives the real Node AES-256-GCM `SecretVault`.

```bash
python3.11 examples/vps-handoff-no-raw-keys/demo.py
# → RESULT: PASS
```

### Demo 2 — Cross-device task delegation with human approval

Laptop sends a signed `review auth module` task plus an attached file to the VPS receiver. The VPS receiver polls its inbox, prompts the operator to accept or reject, then sends a result back via `tasks/result`.

```bash
# terminal 1 — receiver
python3.11 examples/cross-device-task-delegation/run_vps.py

# terminal 2 — sender
python3.11 examples/cross-device-task-delegation/run_laptop.py
```

### Demo 3 — Low-trust agent blocked by capability gate

An unsigned message, a forged signature, and a low-reputation sender all hit the receiver. All three are rejected or redacted at the gate; the receiver then accepts a legitimate task to prove the gates didn't break it.

```bash
python3.11 examples/malicious-sender-rejection/demo.py
# → RESULT: PASS
```

---

## Installation

> Prereqs: **Python 3.11+**, **Rust 1.80+**, **Node 20+** with **npm 10+**.

```bash
git clone https://github.com/jaisogani-ai/synapse.git
cd synapse

# JS / vault MCP
npm install
npm --workspace @synapse/secret-vault-mcp run build

# Python SDK + CLI + adapters
pip install -e ".[dev]"

# Rust daemon
cargo build --release

# Sanity check — should be 136/136
cargo test
pytest -q
npm test
```

---

## Quick Start

```bash
# Show your local presence
synapse presence get          # → {"status": "online"}

# Send a task with capability gate engaged
synapse send-task --from alice --to bob --task "review auth module"

# Receiver-side: review and accept
synapse inbox list
synapse inbox review <task_id>
synapse inbox accept <task_id> --as bob

# Offline target? Outbox queues automatically.
synapse outbox list           # → see what's pending
synapse outbox flush          # → retry due rows now

# Forensically verify the audit log end-to-end
synapse audit verify          # → {"ok": true, "chained_entries": N, ...}
synapse audit tail -n 20      # → last 20 entries with short entry hashes
synapse audit review          # → who-did-what summary by sender / action

# Quarantine surface (auto-fires after N consecutive Gate-1 failures)
synapse quarantine list
synapse quarantine add <agent_id> --reason "manual block"
synapse quarantine release <agent_id>
```

State lives under `$SYNAPSE_HOME` (default `~/.synapse/`): `identity.json`, `trust.json`, `inbox.db`, `outbox.db`, `audit.jsonl`, `blobs/`. Everything is inspect-friendly with `cat`, `jq`, and `sqlite3`.

---

## Known limitations

> Full table with Impact + Mitigation + Plan: [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

Headlines you should know before adopting:

- **No federation, relay, or discovery service.** You configure each peer's URL by hand in `identity.json`. By design — Synapse is for someone who owns their devices, not a multi-tenant SaaS.
- **Rust `TrustStore` is in-memory.** Daemon restart loses recorded outcomes. The Python store is authoritative in v0.1.0-alpha.
- **No end-to-end payload encryption.** A2A messages are HMAC-signed (integrity) and capability-gated, but not encrypted. Use HTTPS / Tailscale / WireGuard / SSH on hostile networks.
- **No mutual TLS, no DID-spec identity.** Per-agent HMAC secrets are the trust root.
- **No anomaly / behaviour / risk-scoring engine.** What v0.1 ships is: HMAC signature gate, reputation gate, capability gate, hash-chained audit, AES-256-GCM vault, static secret detector. That's it.
- **No CI workflow yet.** Tests must be run locally before push (`cargo test && pytest && npm test`). Planned for v0.2.

---

## Roadmap

Full plan: [`docs/ROADMAP.md`](docs/ROADMAP.md). Short version:

- **v0.1.0-alpha (now)** — everything in the [Features](#features) table.
- **v0.2** — Persistent Rust trust store (SQLite-backed) · Endpoint hash pinning · Per-sender rate limit · Vault-client encrypt-at-rest · Inbox WAL · GitHub Actions CI.
- **Beyond v0.2 (open questions, not committed)** — Asymmetric (Ed25519) tokens · Optional end-to-end payload encryption · Rust-native identity + vault.

Synapse will **not** be a federation framework, a memory layer, an agent runtime, a multi-tenant SaaS, an "agent OS", or a marketplace. Listed in [`docs/ROADMAP.md`](docs/ROADMAP.md) under Non-goals.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, code style, PR checklist, and project scope. Code of conduct: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

Security reports go via [`SECURITY.md`](SECURITY.md) (not GitHub Issues).

## License

Apache 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

Free for personal and commercial use. Attribution required per `NOTICE`.

---

<sub>Built by Jai Sogani. The repo is small on purpose.</sub>
