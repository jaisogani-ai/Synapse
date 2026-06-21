<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

<div align="center">

# 🔐 Synapse

### Your AI agents can already talk to each other.<br>They have no idea who they're talking to.

Trusted A2A for Claude Code, Cursor, Codex, Antigravity, VS Code — and anything else that speaks the A2A spec.

> **⚠️ Synapse v0.1.0-alpha.** This is an early, open-source release. The trust
> primitives (identity, reputation, vault, capability gate) are implemented and
> tested. Synapse is **not** hardened for unattended deployments — there is
> no SLA, no security advisory pipeline yet, and several follow-ups are
> listed openly in [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md). Break
> things, open issues.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-128%2F128-brightgreen.svg)](#tests)
[![Rust](https://img.shields.io/badge/daemon-Rust%201.80%2B-orange.svg)](daemon/)
[![Python](https://img.shields.io/badge/SDK-Python%203.11%2B-green.svg)](packages/synapse-core/)
[![A2A](https://img.shields.io/badge/A2A-spec--compliant-purple.svg)](https://a2aproject.org)
[![Self-hosted](https://img.shields.io/badge/deployment-self--hosted-lightgrey.svg)](#quick-start)

<video src="assets/demo.mp4" controls muted loop autoplay playsinline width="800">
  Your browser does not support the HTML video tag.
  <a href="assets/demo.mp4">Download the demo video</a>, or view the
  <a href="assets/demo.gif">animated GIF</a>.
</video>

</div>

---

## What problem does Synapse solve?

Today, when Claude Code on your laptop sends a task to Codex on your VPS, **anything in between can:**

- Forge the request — there's no identity check
- Read the credential — it's in the payload
- Replay the message — there's no expiry
- Pretend to be the target — there's no verification
- Escalate privilege — there's no capability check

A2A defines the *envelope*. It doesn't tell you who's on either end of it, what they're allowed to do, whether you should trust them, or how to hand them a secret without leaking it.

**Synapse is the trust layer.** Identity. Reputation. Capabilities. Vault. Audit. All bolted onto the A2A protocol you already use.

```
Without Synapse:           With Synapse:

Claude Code on laptop      Claude Code on laptop
       │                          │
       │  unsigned, unaudited     │  signed JWT + HMAC payload
       │  raw API key in body     │  scoped vault proxy, never raw key
       │  no capability check     │  caps verified per RPC method
       ▼                          ▼
Codex on VPS               Codex on VPS
   "Trust me, I'm           "Identity verified.
    Alice."                  Reputation 0.91.
                             Capability granted.
                             Audited."
```

---

## How it works

```
┌──────────────────────────────────────────────────────────┐
│            SYNAPSE DAEMON  (Rust)                          │
│  • Trust store — reputation scoring per agent + domain   │
│  • Internal IPC over Unix socket (daemon ↔ local CLI)    │
│  • Capability enforcement — every trust op is gated      │
└──────────────────────────────────────────────────────────┘
        ▲                                            ▲
        │ identity / vault / trust queries           │
        │                                            │
┌──────────────────────┐                ┌────────────────────────┐
│ packages/synapse-cli │                │ packages/synapse-      │
│  • send-task         │                │  vault-mcp (Node)      │
│  • inbox / outbox    │                │  AES-256-GCM vault     │
│  • presence          │                │  Scoped proxy tokens   │
│  • review            │                │  Append-only audit     │
└──────────┬───────────┘                └────────────────────────┘
           │
           │   standard A2A protocol  (JSON-RPC over HTTP,
           │   signed with HMAC-SHA256, capability JWT in header)
           ▼
       Other agent on another device
```

> **A2A is the wire format. Synapse is the trust layer.** Synapse does **not** replace A2A or invent a new protocol. We sign and verify A2A messages, gate them with capabilities, and route credential-touching ones through a vault.

---

## Tests

| Suite | Result | What's covered |
|---|---|---|
| `cargo test` | **39 / 39** ✅ | Rust daemon — trust store, IPC, protocol codec, capability gate |
| `pytest` | **79 / 79** ✅ | Python SDK + 5 adapters + CLI — identity, vault, A2A, outbox, presence, **capability enforcement** |
| `npm test` (vault-mcp) | **10 / 10** ✅ | TypeScript AES-256-GCM vault — round-trip, tamper detection, proxy expiry |
| **Total** | **128 / 128** | |

End-to-end demos pass live:

- `examples/vps-handoff-no-raw-keys/demo.py` — RESULT: PASS
- Outbox e2e (offline → queue → retry → deliver → dead → requeue) — green
- Blob e2e (1 MiB, chunked Range fetch, resume, sha256 tamper-reject) — green

---

## What's inside

| Pillar | What it does | Where it lives |
|---|---|---|
| **Identity** | Cryptographic agent identity, HS256 JWT with capability claims, HMAC-SHA256 request signing | [`packages/synapse-core/synapse/security/zero_trust.py`](packages/synapse-core/synapse/security/zero_trust.py) |
| **Vault** | Scoped, time-limited credential proxies; AES-256-GCM at rest; raw secret never on the wire; append-only audit | [`packages/synapse-vault-mcp/src/vault.ts`](packages/synapse-vault-mcp/src/vault.ts) |
| **Trust** | Reputation scoring per agent + domain; outcome-weighted; redacts content from low-rep senders | [`packages/synapse-cli/synapse_cli/trust.py`](packages/synapse-cli/synapse_cli/trust.py), [`daemon/src/trust/`](daemon/src/trust/) |
| **Capability gate** | Every A2A method requires a specific capability; sender's JWT must grant it; subject must match HMAC sender | [`packages/synapse-cli/synapse_cli/receiver.py`](packages/synapse-cli/synapse_cli/receiver.py), [`daemon/src/security/capability.rs`](daemon/src/security/capability.rs) |
| **A2A integration** | Standard A2A JSON-RPC over HTTP; spec-compliant `FilePart` with `uri` for large files | [`packages/synapse-cli/synapse_cli/a2a.py`](packages/synapse-cli/synapse_cli/a2a.py) |
| **Durable outbox** | Offline target → SQLite queue → background worker retries with exponential backoff → DLQ after 6 attempts | [`packages/synapse-cli/synapse_cli/outbox_store.py`](packages/synapse-cli/synapse_cli/outbox_store.py) |
| **Chunked file transfer** | Files > 256 KiB served via content-addressed blob endpoint with HTTP `Range` resume + sha256 verify | [`packages/synapse-cli/synapse_cli/blob.py`](packages/synapse-cli/synapse_cli/blob.py) |
| **Presence** | `online` / `busy` / `offline` — `GET /presence`, no CRDT, no gossip | [`packages/synapse-cli/synapse_cli/presence.py`](packages/synapse-cli/synapse_cli/presence.py) |
| **Inbox + review** | SQLite-backed received-task queue; operator can review content before accept | [`packages/synapse-cli/synapse_cli/inbox_store.py`](packages/synapse-cli/synapse_cli/inbox_store.py) |
| **Audit log** | Append-only JSONL of every send / receive / accept / reject / capability denial | [`packages/synapse-cli/synapse_cli/audit.py`](packages/synapse-cli/synapse_cli/audit.py) |

### Adapters (already in repo)

5 platform adapters — Claude Code, Cursor, Codex, VS Code, Antigravity — each ~30 LOC subclassing [`BaseAdapter`](packages/adapters/base.py). Each provides identity registration, trust signing, vault credential routing, and A2A signing. **42 adapter tests pass.**

---

## Demos

> Live in [`examples/`](examples/). Each runs end-to-end against the real code paths — no in-process simulation of vault, signing, or capability gate.

### 1 — VPS deploy with no raw credentials

`![demo-deploy](assets/demo-deploy.gif)` *(placeholder — record per `examples/vps-handoff-no-raw-keys/README.md`)*

Codex on a VPS deploys an app using an Anthropic API key. The key never leaves the laptop's vault; the VPS sees only a 300-second proxy URL. Drives the real Node AES-256-GCM `SecretVault`.

```bash
python3.11 examples/vps-handoff-no-raw-keys/demo.py
```

### 2 — Cross-device task delegation with human approval

`![demo-review](assets/demo-review.gif)` *(placeholder — record per `examples/cross-device-task-delegation/README.md`)*

Laptop sends a signed "review auth module" task plus an attached file to the VPS receiver. The VPS receiver polls its inbox, prompts the operator to accept or reject, then sends a result back via `tasks/result`. The README shows you the rich version of this flow; the demo runs the message path end-to-end with HMAC signing, capability gate, and audit log.

```bash
# terminal 1 — receiver
python3.11 examples/cross-device-task-delegation/run_vps.py

# terminal 2 — sender
python3.11 examples/cross-device-task-delegation/run_laptop.py
```

### 3 — Low-trust agent blocked by capability gate

`![demo-block](assets/demo-block.gif)` *(placeholder — record per `examples/malicious-sender-rejection/README.md`)*

An unsigned message, a forged signature, and a low-reputation sender all hit the receiver. All three are rejected or redacted at the gate, audited as `reject_unsigned` / `reject_capability` / `receive_task` (with content redacted in `inbox list`). The receiver then accepts a legitimate task to prove the gates didn't break it.

```bash
python3.11 examples/malicious-sender-rejection/demo.py
```

---

## Feature comparison

| | **Synapse** | A2A (raw spec) | CrewAI | AutoGen | LangGraph | Supermemory |
|---|---|---|---|---|---|---|
| Standard A2A wire format | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Cryptographic agent identity | ✅ HMAC + JWT | ❌ | ❌ | ❌ | ❌ | ❌ |
| Per-method capability gate | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Reputation scoring | ✅ confidence-weighted | ❌ | ❌ | ❌ | ❌ | ❌ |
| Scoped credential proxies (vault) | ✅ AES-256-GCM | ❌ | ❌ | ❌ | ❌ | ❌ |
| Durable outbox + retry | ✅ | ❌ | ❌ | ❌ | ⚠️ in-mem | ❌ |
| Chunked + resumable file transfer | ✅ Range + sha256 | ⚠️ base64 only | ❌ | ❌ | ❌ | ❌ |
| Append-only audit log | ✅ | ❌ | ⚠️ unstructured | ⚠️ unstructured | ⚠️ unstructured | ❌ |
| Cross-device / cross-account | ✅ | ✅ | ❌ same process | ❌ same process | ❌ same process | ❌ |
| Memory layer | ❌ (not our problem) | ❌ | ❌ | ❌ | ⚠️ | ✅ |
| Self-hosted | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ paid SaaS |
| Open source | ✅ Apache-2.0 | ✅ | ✅ | ✅ | ✅ | ❌ |

Synapse is not trying to be a memory framework, an orchestration framework, or an agent runtime. It assumes you already have those. It's the **trust + transport security layer** for the A2A messages those tools already send.

---

## Why Synapse exists

I own a laptop, a desktop, a VPS, and a second Anthropic account on a separate machine. I wanted the AI tools on all four of those devices to send each other tasks, files, and results without exposing my API keys, without trusting the network, and without re-implementing JWT/HMAC/key rotation by hand in every adapter.

A2A solves the format. It does not solve any of the trust questions. Synapse is the smallest possible answer to those questions.

It is deliberately **not**:

- a new wire protocol
- a federation framework
- a memory layer
- an agent OS
- an orchestration framework
- a hosted SaaS

It is one Rust daemon + one Python SDK + one Node MCP + a CLI. Total ~7 KLoC of real code (excluding tests). [Apache 2.0](LICENSE).

---

## Security model

Synapse enforces **three gates** on every inbound A2A message. Failure at any gate stops the message and logs to the audit trail.

```
   inbound message
        │
        ▼
  ┌─────────────┐
  │  Gate 1     │  Valid HMAC-SHA256 signature from known agent?
  │  Signature  │  Timestamp within 300s replay window?
  └──────┬──────┘
         │ pass
         ▼
  ┌─────────────┐
  │  Gate 2     │  Sender reputation ≥ threshold (default 0.5)?
  │  Reputation │  If not, content is redacted until explicit accept.
  └──────┬──────┘
         │ pass
         ▼
  ┌─────────────┐
  │  Gate 3     │  Does the sender's JWT grant `a2a.send_task`
  │  Capability │  (or the cap required by the RPC method)?
  └──────┬──────┘  Does the token's `sub` match the HMAC sender?
         │ pass
         ▼
     process task
```

Full threat model, attack classes, fixed issues, and known limitations live in [`SECURITY_REVIEW.md`](SECURITY_REVIEW.md). Vulnerability reporting in [`SECURITY.md`](SECURITY.md).

---

## Quick Start

> Prereqs: Python 3.11+, Rust 1.80+, Node 20+, npm 10+.

```bash
# 1 — clone and install
git clone https://github.com/jaisogani-ai/synapse.git
cd synapse
npm install                       # workspace deps (vault MCP)
npm --workspace @synapse/secret-vault-mcp run build
pip install -e ".[dev]"           # Python SDK + CLI

# 2 — build the daemon
cargo build --release

# 3 — sanity check
cargo test                        # 39 passing
pytest -q                         # 79 passing
npm test                          # 10 passing

# 4 — run the marquee demo
python3.11 examples/vps-handoff-no-raw-keys/demo.py
```

### Send your first task

```bash
# register a target agent's endpoint (one-time)
synapse presence list             # → []

# send-task with capability gate engaged
synapse send-task --from alice --to bob --task "review auth module"

# bob reviews and accepts
synapse inbox list
synapse inbox review <task_id>
synapse inbox accept <task_id> --as bob

# offline target? outbox queues automatically.
synapse outbox list               # see what's pending
synapse outbox flush              # retry now
```

---

## Examples

| Path | What it shows |
|---|---|
| [`examples/vps-handoff-no-raw-keys/`](examples/vps-handoff-no-raw-keys/) | Real AES-256-GCM vault, scoped proxy, zero raw-key exposure |
| [`examples/cross-device-task-delegation/`](examples/cross-device-task-delegation/) | Two-terminal walkthrough — laptop sends, VPS receives, result returns |
| [`examples/malicious-sender-rejection/`](examples/malicious-sender-rejection/) | Forged signature, missing capability, low-rep redaction — all three rejected |

Place demo recordings at:

```
assets/demo-deploy.gif    — VPS deploy demo
assets/demo-review.gif    — patch-review demo
assets/demo-block.gif     — capability denial demo
assets/demo-1.png         — terminal screenshot from demo 1
assets/demo-2.png         — terminal screenshot from demo 2
assets/demo-3.png         — terminal screenshot from demo 3
```

Recording instructions per demo live in each demo's `README.md`.

---

## Known limitations

> Full list with explanations and mitigations: [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

Headlines:

- **No federation, no relay, no discovery.** You configure each peer's URL manually in `identity.json`. By design — Synapse is for someone who owns their devices, not a multi-tenant SaaS.
- **Rust `TrustStore` is in-memory.** Restart loses recorded outcomes. Python store is persisted; for v0.1.0-alpha it is the authoritative trust store.
- **No end-to-end payload encryption.** A2A messages are signed (HMAC) and capability-gated, but not encrypted. Use HTTPS or a tunnel (Tailscale, WireGuard, SSH) on hostile networks.
- **Capability strings are advisory.** A token granting `vault.store_secret` only matters if the vault MCP checks it. The receiver checks A2A method caps; downstream MCPs must enforce their own.

---

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md). Short version: **v0.1 is an alpha** that ships the trust primitives (identity, reputation, vault, capability gate) plus the A2A transport surface, with tests and demos. v0.2+ is a small, honest list — SQLite-backed trust store, end-to-end payload encryption, CI — if real use earns them.

---

## License

Apache 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

Free for personal and commercial use. Attribution required per NOTICE.

---

<sub>Built by Jai Sogani. The repo is small on purpose.</sub>
