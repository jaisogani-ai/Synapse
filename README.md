<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

<div align="center">

<img src="assets/hero.png" alt="Synapse — Trusted A2A for Claude Code, Cursor, Codex, Antigravity, VS Code" width="920">

# 🔐 Synapse

### Your AI agents can already talk to each other.<br>They have no idea who they're talking to.

Trusted A2A for **Claude Code, Cursor, Codex, Antigravity, VS Code** — and anything else that speaks the A2A spec.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](packages/synapse-core/)
[![Rust](https://img.shields.io/badge/Rust-1.80%2B-CE412B.svg?logo=rust&logoColor=white)](daemon/)
[![TypeScript](https://img.shields.io/badge/TypeScript-Node%2020%2B-3178C6.svg?logo=typescript&logoColor=white)](packages/synapse-vault-mcp/)
[![Tests](https://img.shields.io/badge/tests-194%2F194-brightgreen.svg)](#tests)
[![A2A](https://img.shields.io/badge/A2A-spec--compliant-7C3AED.svg)](https://a2aproject.org)

![Synapse demo](assets/demo.gif)

</div>

> **⚠️ Synapse v0.1.0-alpha.** Early open-source release. The trust primitives
> (identity, reputation, vault, capability gate, hash-chained audit, mTLS,
> end-to-end encryption, patch review) are implemented and tested. This is an
> alpha — there is no SLA, and remaining gaps are listed openly in
> [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md). Break things, open issues.

---

## Demo

Watch Synapse hand off a credential between devices without the secret ever leaving the vault.

<div align="center">

<video src="assets/synapse-demo.mp4" controls muted loop autoplay playsinline width="920">
  Your browser does not support the HTML video tag.
  <a href="assets/synapse-demo.mp4">Download the 45-second demo</a> or
  <a href="assets/demo.gif">view the animated GIF fallback</a>.
</video>

<sub>45 seconds · 1280×720 · audio included. If the video doesn't render in your viewer, the GIF above plays the same content.</sub>

</div>

---

## Problem

When Claude Code on your laptop sends a task to Codex on your VPS today, **anything in between can:**

- forge the request — there's no identity check
- read the credential — it's in the payload
- replay the message — there's no expiry
- pretend to be the target — there's no verification
- escalate privilege — there's no capability check
- silently rewrite the audit log — there's no tamper evidence

A2A defines the message envelope. It does not tell you who's on either end of it, what they're allowed to do, whether you should trust them, how to hand them a secret without leaking it, or how to prove later that nothing was tampered with.

**Synapse is the trust layer.** Identity, reputation, capabilities, vault, hash-chained audit, optional mTLS and end-to-end encryption — bolted onto the A2A protocol you already use.

---

## How it works

```
Without Synapse:            With Synapse:

Claude Code on laptop       Claude Code on laptop
       │                           │
       │  unsigned, unaudited      │  HMAC-signed envelope + capability JWT
       │  raw API key in body      │  vault proxy URL (raw secret never leaves)
       │  no capability check      │  caps verified per RPC method
       │  no replay window         │  ±300 s timestamp drift window
       │  audit can be rewritten   │  hash-chained — tampering is detectable
       │  cleartext on the wire    │  optional mTLS + end-to-end encryption
       ▼                           ▼
Codex on VPS                Codex on VPS
   "Trust me, I'm            "Identity verified.
    Alice."                   Reputation 0.91.
                              Capability granted.
                              Audit row #4327 chained."
```

A2A is the wire format. Synapse is the trust layer. We **sign and verify** A2A messages, **gate** them with capabilities, **route** credential-touching ones through a vault, and **record** every decision in a tamper-evident log. We do not fork or replace A2A.

---

## Architecture diagram

<div align="center">

<img src="assets/architecture.png" alt="Synapse architecture — agents, Synapse Core, security agents, execution environments" width="920">

</div>

> **Diagram disclosure (read this).** The diagrams above show the v0.1.0-alpha
> design at a glance and use compact marketing labels. Below is the exact
> mapping from label → what ships today, so a reviewer can verify every claim.
>
> ✅ **Implemented and tested in v0.1.0-alpha:** Identity (per-agent HMAC +
> HS256 JWT) · Device Identity in `did:synapse:<agent_id>` format · Trust &
> Reputation (confidence-weighted) · Vault & Secrets (AES-256-GCM + scoped
> proxies) · A2A Messaging · Audit & Logging (**hash-chained, forensically
> verifiable**) · Capability Enforcement (per RPC method + per Rust IPC
> TrustOp) · Secret Detector (140+ patterns) · Risk Scoring (reputation) ·
> Policy Enforcement (capability gate) · Anomaly Detection (per-sender rate
> Z-score) · Threat Response (auto-quarantine) · Quarantine & Isolation ·
> Access Review · Continuous Verification (every message walks all three
> gates) · **Mutual TLS** (opt-in) · **End-to-End Encryption** (opt-in,
> X25519+AES-256-GCM) · File Transfer (chunked, resumable) · Presence ·
> Inbox Review · Outbox & Retry · Patch Review Workflow.
>
> ❌ **Not implemented yet:** full W3C DID-method registry · "Behaviour
> Analysis" as a *learned* ML model (we ship statistical reputation, not a
> trained model).
>
> ⚠️ **Words in the diagram this README does NOT claim:** "Enterprise Grade",
> "Production Ready". Synapse is **v0.1.0-alpha** — those would be inaccurate.
> Full honest gap list: [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

Text-based, source-true flow diagrams (high-level, identity, vault, A2A task, capability, trust) live in [`docs/diagrams/`](docs/diagrams/).

---

## Features

Everything below is wired up, tested, and demonstrated. No placeholders.

| Pillar | What it does | Where it lives |
|---|---|---|
| **Identity** | Per-agent HMAC-SHA256 secrets, HS256 JWTs with capability claims, 15-min TTL, `did:synapse:` identifiers | [`zero_trust.py`](packages/synapse-core/synapse/security/zero_trust.py), [`device_identity.py`](packages/synapse-core/synapse/security/device_identity.py) |
| **Vault** | AES-256-GCM at rest, scoped time-limited proxy URLs, raw secret never on the wire, append-only audit | [`vault.ts`](packages/synapse-vault-mcp/src/vault.ts) |
| **Trust + reputation** | Confidence-weighted scoring per agent + domain; low-rep content redacted until accept | [`trust.py`](packages/synapse-cli/synapse_cli/trust.py), [`daemon/src/trust/`](daemon/src/trust/) |
| **Capability enforcement** | Per RPC method on the receiver, per TrustOp on the Rust IPC dispatcher; JWT must grant the cap and `sub` must match the HMAC sender | [`receiver.py`](packages/synapse-cli/synapse_cli/receiver.py), [`daemon/src/ipc/mod.rs`](daemon/src/ipc/mod.rs) |
| **A2A integration** | Standard JSON-RPC over HTTP; spec-compliant `FilePart` with `uri` for large files | [`a2a.py`](packages/synapse-cli/synapse_cli/a2a.py) |
| **Hash-chained audit** | Append-only JSONL; each row carries `prev_hash` + `entry_hash`; `synapse audit verify` detects modified / deleted / forged rows | [`audit.py`](packages/synapse-cli/synapse_cli/audit.py) |
| **Mutual TLS** | Opt-in self-signed mTLS; `synapse identity gen-cert`; receiver requires + verifies the client cert | [`mtls.py`](packages/synapse-cli/synapse_cli/mtls.py) |
| **End-to-end encryption** | Opt-in X25519 + HKDF + AES-256-GCM sealed envelopes; only the recipient's private key decrypts, independent of transport; forward-secret | [`e2e.py`](packages/synapse-cli/synapse_cli/e2e.py) |
| **Patch review workflow** | Reviewer returns a unified diff; sender applies it with strict context validation, or comments → revises → resubmits in a threaded loop | [`patch.py`](packages/synapse-cli/synapse_cli/patch.py) |
| **Durable outbox** | Offline target → SQLite queue → background worker, exponential backoff, DLQ after 6 attempts | [`outbox_store.py`](packages/synapse-cli/synapse_cli/outbox_store.py) |
| **Chunked file transfer** | Files > 256 KiB via content-addressed blob endpoint, HTTP `Range` resume, sha256 end-to-end verify | [`blob.py`](packages/synapse-cli/synapse_cli/blob.py) |
| **Quarantine + threat response** | Auto-block after 5 consecutive Gate-1 failures; manual `synapse quarantine` | [`quarantine.py`](packages/synapse-core/synapse/security/quarantine.py), [`threat_response.py`](packages/synapse-core/synapse/security/threat_response.py) |
| **Anomaly detection** | Per-sender rate Z-score over a 60 s sliding window | [`anomaly.py`](packages/synapse-core/synapse/security/anomaly.py) |
| **Access review** | `synapse audit review` summarizes the log by sender / receiver / action | [`access_review.py`](packages/synapse-core/synapse/security/access_review.py) |
| **Presence** | `online` / `busy` / `offline` over `GET /presence`; no CRDT, no gossip | [`presence.py`](packages/synapse-cli/synapse_cli/presence.py) |
| **Inbox + review** | SQLite-backed received-task queue; `synapse inbox review` shows content before accept/reject | [`inbox_store.py`](packages/synapse-cli/synapse_cli/inbox_store.py) |
| **5 platform adapters** | Claude Code, Cursor, Codex, VS Code, Antigravity — each ~30 LOC on `BaseAdapter`; 42 tests | [`packages/adapters/`](packages/adapters/) |

### Tests

| Suite | Result | Command |
|---|---|---|
| `cargo test` | **39 / 39** ✅ | `cargo test` |
| `pytest` | **145 / 145** ✅ | `PYTHONPATH=… python3.11 -m pytest tests packages/adapters packages/synapse-cli/tests -q` |
| `npm test` (vault MCP) | **10 / 10** ✅ | `(cd packages/synapse-vault-mcp && npm test)` |
| **Total** | **194 / 194** | |

---

## Security model

Three gates on every inbound A2A message. Failure at any gate stops the message and writes a hash-chained audit row.

```
   inbound A2A message
        │
        ▼
  ┌─────────────┐   Gate 1: HMAC-SHA256 signature valid?
  │  SIGNATURE  │ → Timestamp within ±300 s? (replay window)
  └──────┬──────┘    reject_unsigned / reject_bad_signature
         ▼
  ┌─────────────┐   Gate 2: sender reputation ≥ threshold (default 0.5)?
  │  REPUTATION │ → Low-rep content is redacted in the inbox until accept.
  └──────┬──────┘
         ▼
  ┌─────────────┐   Gate 3: sender's JWT grants the method's required cap?
  │  CAPABILITY │ → Does the token's sub match the HMAC sender?
  └──────┬──────┘    reject_capability
         ▼
     dispatch → hash-chained audit row
```

On top of the gates, optionally: **mTLS** (transport confidentiality) and **end-to-end encryption** (payload confidentiality, independent of transport).

Full threat model, attack classes (spoofing, replay, secret leakage, capability escalation, impersonation, audit tampering, DoS), fixed issues, and assumptions: [`SECURITY_REVIEW.md`](SECURITY_REVIEW.md). Vulnerability reporting: [`SECURITY.md`](SECURITY.md).

---

## Screenshots

Real CLI output — these are what the features actually print today.

### Vault handoff (zero raw-key exposure)

```
┌─ STEP 3: VPS REQUESTS SCOPED CREDENTIAL PROXY (TTL=300s)
│  ✓ Proxy issued: synapse+vault://proxy/245c5a8ab7d4…
│  ⚠ Agent receives ONLY the proxy URL. Never the raw key.
└─ STEP 5: AUDIT LOG (FROM REAL VAULT) — ZERO RAW KEY EXPOSURE
│  store           anthropic-api
│  issue_proxy     anthropic-api  (production deploy via codex)
│  resolve_proxy   anthropic-api
│  ✓ No 'retrieve' actions — agent never touched the real key
```

### Trust log (hash-chained, forensically verifiable)

```
$ synapse audit verify
{ "ok": true, "chained_entries": 7, "unchained_entries": 0,
  "tampered_at_index": -1, "reason": "chain intact" }

$ synapse audit verify          # after someone edits a past row
{ "ok": false, "tampered_at_index": 3,
  "reason": "entry_hash mismatch at index 3: content does not match recorded digest" }
```

### Inbox review (human-in-the-loop before accept)

```
$ synapse inbox review 31857898-1c83-418f-b3b7-63178478c098
{ "sender": "alice", "sender_score": 0.9, "status": "pending",
  "text": "review auth module",
  "attachments": [ { "name": "auth.rs", "sha256": "2597…", "size": 1048576 } ] }
```

---

## Examples

Live in [`examples/`](examples/). Each runs end-to-end against the real code paths — no in-process simulation of the vault, signing, or capability gate.

### Demo 1 — VPS deploy with no raw credentials

```bash
python3.11 examples/vps-handoff-no-raw-keys/demo.py   # → RESULT: PASS
```

Codex on a VPS deploys using an Anthropic API key. The key never leaves the laptop's vault; the VPS sees only a 300-second proxy URL. Drives the real Node AES-256-GCM `SecretVault`.

### Demo 2 — Patch review across devices

```bash
python3.11 examples/cross-device-task-delegation/run_vps.py     # terminal 1
python3.11 examples/cross-device-task-delegation/run_laptop.py  # terminal 2
```

Laptop sends a signed review task; the reviewer returns a unified diff; the laptop applies it with context validation, or comments → revise → resubmit until accepted. Signed, capability-gated, audited throughout.

### Demo 3 — Low-trust agent blocked

```bash
python3.11 examples/malicious-sender-rejection/demo.py   # → RESULT: PASS
```

An unsigned message, a forged signature, and a low-reputation sender all hit the receiver. All three are rejected or redacted at the gate; the receiver then accepts a legitimate task to prove the gates didn't break it.

---

## Installation

> Prereqs: **Python 3.11+**, **Rust 1.80+**, **Node 20+** with **npm 10+**.

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

## Quick Start

```bash
# Send a task with the capability gate engaged
synapse send-task --from alice --to bob --task "review auth module"

# Receiver-side: review, then accept
synapse inbox list
synapse inbox review <task_id>
synapse inbox accept <task_id> --as bob

# Offline target? The outbox queues + retries automatically.
synapse outbox list
synapse outbox flush

# Forensically verify the audit log end-to-end
synapse audit verify
synapse audit review

# Patch review workflow
synapse patch make --old before.py --new after.py --name auth.py > change.diff
synapse patch summarize --patch change.diff
synapse patch apply auth.py --patch change.diff --dry-run    # validate first
synapse patch apply auth.py --patch change.diff              # apply (context-checked)

# End-to-end encrypt a task to a peer (needs their X25519 public key)
synapse identity gen-keypair alice
synapse send-task --from alice --to bob --task "..." --encrypt

# Quarantine surface (auto-fires after repeated signature failures)
synapse quarantine list
synapse quarantine release <agent_id>
```

State lives under `$SYNAPSE_HOME` (default `~/.synapse/`): `identity.json`, `trust.json`, `inbox.db`, `outbox.db`, `audit.jsonl`, `blobs/`, `certs/`, `keys/`. All inspect-friendly with `cat`, `jq`, and `sqlite3`.

---

## Known limitations

> Full table with Impact + Mitigation + Plan: [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

Headlines you should know before adopting:

- **No federation, relay, or discovery service.** You configure each peer's URL by hand in `identity.json`. By design — Synapse is for someone who owns their devices, not a multi-tenant SaaS.
- **Rust `TrustStore` is in-memory.** Daemon restart loses recorded outcomes. The Python store is authoritative in v0.1.0-alpha.
- **mTLS and E2E encryption are opt-in.** The default A2A path is HMAC-signed over HTTP. Turn on mTLS / E2E / a tunnel for confidentiality on hostile networks.
- **mTLS is self-signed** with manual cert distribution — no CA / revocation infrastructure yet.
- **No CI workflow yet.** Run `cargo test && pytest && npm test` locally before pushing. Planned for v0.2.

---

## Roadmap

Full plan: [`docs/ROADMAP.md`](docs/ROADMAP.md). Short version:

- **v0.1.0-alpha (now)** — everything in the [Features](#features) table.
- **v0.2** — persistent Rust trust store (SQLite) · endpoint hash pinning · per-sender rate limit · vault-client encrypt-at-rest · inbox WAL · GitHub Actions CI.
- **Beyond v0.2 (open questions, not committed)** — asymmetric (Ed25519) tokens · full W3C DID method · CA-backed mTLS.

Synapse will **not** become a federation framework, a memory layer, an agent runtime, a multi-tenant SaaS, an "agent OS", or a marketplace. Non-goals are listed in [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, code style, PR checklist, and scope. Code of conduct: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Security reports go via [`SECURITY.md`](SECURITY.md), not GitHub Issues.

## License

Apache 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Free for personal and commercial use. Attribution required per `NOTICE`.

---

<sub>Built by Jai Sogani. The repo is small on purpose.</sub>
