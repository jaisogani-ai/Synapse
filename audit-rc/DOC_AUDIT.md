# DOC_AUDIT

**Date:** 2026-06-21
**Method:** Read every documentation file in full, then grep-walked the source tree for the symbols / files each doc references.

Each section: **State** (exists / non-empty / accurate), then **Mismatches** — concrete code-vs-doc divergences, file:line cited where applicable.

---

## README.md (root)

**State**

| Check | Result |
|-------|--------|
| Exists | yes |
| Non-empty | yes (106 lines) |
| Top-of-file headline + tagline | yes |
| License section | yes (links `LICENSE` and `NOTICE`) |

**Mismatches**

| # | Claim | Reality | Severity |
|---|-------|---------|----------|
| R-1 | `> **Status:** Phase D (complete)` (line 16) | `packages/synapse-cli/synapse_cli/__main__.py` is a stub that prints `"Stub: would send..."`. The published CLI surface does not work end-to-end. | HIGH |
| R-2 | `daemon/src/identity/` `daemon/src/vault/` `daemon/src/a2a_signer/` shown in the tree as "(Phase C)" (lines 51–52) | **All three directories are empty.** Listing them in the tree implies WIP that does not exist. | MEDIUM |
| R-3 | "5 adapters — Claude Code, Cursor, Codex, VS Code, Antigravity" (line 57) with the implication of tool-specific integration | Every adapter is a 25-line subclass of `BaseAdapter` that sets `tool_type` and nothing else. Behaviour is 100% identical across adapters. | MEDIUM |
| R-4 | Build & test block shows `~/.cargo/bin/cargo build` (line 85) | Hard-codes a path that exists on the maintainer's machine. New contributors hit "command not found" or use the wrong toolchain. Use `cargo` (PATH) instead. | LOW |
| R-5 | The 4-pillar table calls out "A2A Integration" as living in `daemon/src/protocol/`, `daemon/src/ipc/` (line 26) | The daemon's protocol is the **Synapse Protocol**, not A2A. A2A signing/verification lives in **Python** (`packages/synapse-cli/synapse_cli/a2a_signer.py`, `transport.py`, `receiver.py`). The daemon does not see A2A messages. | HIGH |

---

## docs/ARCHITECTURE.md

**State**

| Check | Result |
|-------|--------|
| Exists | yes |
| Non-empty | yes (3,873 B / 84 lines) |
| Component diagram | yes |
| Module table | yes |

**Mismatches**

| # | Claim | Reality | Severity |
|---|-------|---------|----------|
| A-1 | `> Phase B — the four-pillar foundation.` (line 6) | `ROADMAP.md` is on Phase D. ARCHITECTURE.md was last updated to describe Phase B and never refreshed. | HIGH |
| A-2 | "Identity ... Implementation: `packages/synapse-core/synapse/security/zero_trust.py`" (lines 32–33) | True. **However**, the same doc's diagram (lines 15–23) shows the daemon as the source of identity — but the daemon has zero identity code. The identity primitive lives in Python and is *used* by the CLI/adapters, not the daemon. | HIGH |
| A-3 | "Vault ... Implementation: `packages/synapse-vault-mcp/src/vault.ts`" (line 40) | The TS vault is real. **But** `packages/synapse-cli/synapse_cli/vault_client.py` is a plaintext in-memory `dict` that *also* claims to "mirror the MCP server" (line 37 of that file). Two divergent vault implementations is not flagged anywhere. | HIGH |
| A-4 | "Trust ... Implementation: `daemon/src/trust/reputation.rs`" (line 48) | True for reputation. The trust score also lives in `packages/synapse-cli/synapse_cli/trust.py` as a separate JSON file. The two stores are not synchronised and `TrustStore` in the CLI does not talk to the daemon. | HIGH |
| A-5 | "A2A Integration ... `daemon/src/protocol/`, `daemon/src/ipc/`" (line 56) | These modules implement the **Synapse Protocol**, not A2A. Same mismatch as `R-5`. | HIGH |
| A-6 | "Daemon modules" table (lines 60–66) lists only 5 modules, omitting that `security/capability.rs` exists but is never called from `ipc::dispatch` | Capability enforcement is code-complete but dormant. The trust model docs imply otherwise. | MEDIUM |
| A-7 | Roadmap table (lines 79–83) ends at Phase E and labels Phase B as "this phase" | Stale — `ROADMAP.md` runs through Phase H and lists D as current. | MEDIUM |

---

## docs/TRUST_MODEL.md

**State**

| Check | Result |
|-------|--------|
| Exists | yes |
| Non-empty | yes (5,335 B / 143 lines) |
| Three-gate diagram | yes |
| Threat model table | yes |

**Mismatches**

| # | Claim | Reality | Severity |
|---|-------|---------|----------|
| T-1 | "Gate 2: Reputation Scoring ... `daemon/src/trust/reputation.rs` (Rust, SQLite-backed)" (line 76) | The Rust store **is** SQLite-backed, but the daemon's `main.rs:28` instantiates it via `TrustStore::new_in_memory()` — **`Connection::open_in_memory()`**. A daemon restart loses all reputation. SQLite-on-disk is implemented (`ReputationMemory::open(path)`) but never used. | HIGH |
| T-2 | Same line also cites `packages/synapse-cli/synapse_cli/trust.py` (Python store) | The CLI trust store is a JSON file with **no signatures, no permissions check, no daemon coordination**. The trust-model promise of "single source of truth" does not hold across the Rust/Python boundary. | HIGH |
| T-3 | "Threat: Replay attacks → Mitigation: JWT `exp` claim enforces 15-minute TTL" (line 137) | After Phase 4 fixes, the actual mitigation is `MAX_TIMESTAMP_DRIFT_SECONDS = 300` on signed payloads. The 15-minute JWT TTL is real but is a separate control. The line conflates the two. | LOW |
| T-4 | "Threat: Key compromise → Mitigation: Per-agent keys; rotation via `issue_identity`" (line 139) | `ZeroTrustNetwork.issue_identity` overwrites `_secrets[agent_id]` — that is rotation. But there is no daemon-side identity store yet (`daemon/src/identity/` is empty), so "per-agent keys" only exists inside one Python process's RAM. | MEDIUM |
| T-5 | "Audit Trail ... single source of truth for forensic analysis" (line 130) | Audit log is plaintext JSONL with no chained hash or signature (`SH-1` in `SECURITY_REVIEW.md`, deferred). Anyone with FS-write can edit, reorder, or delete entries. The "single source of truth" framing overstates the guarantee. | HIGH |
| T-6 | "Supply Chain Verification ... 1. OSV.dev CVE lookup" (lines 113–119) | Code is real (`supply_chain.py`). The doc doesn't mention that a network failure produces no retry/circuit breaker (`L-4` deferred). | LOW |

---

## docs/PROTOCOL.md

**State**

| Check | Result |
|-------|--------|
| Exists | yes |
| Non-empty | yes (2,433 B / 65 lines) |
| Envelope schema | yes |
| Trust ops table | yes |
| Error codes | yes |
| Versioning note | yes |

**Mismatches**

None significant. PROTOCOL.md matches `daemon/src/protocol/mod.rs` 1:1 — same `TrustOp` variants, same error codes, same envelope fields. **This is the only doc that survives reality-check cleanly.**

One observation, not a mismatch: "The normative source is `daemon/src/protocol/mod.rs`" (line 6) is exactly the right framing. Other docs should adopt this pattern.

---

## docs/ROADMAP.md

**State**

| Check | Result |
|-------|--------|
| Exists | yes |
| Non-empty | yes (3,371 B / 87 lines) |
| Phase history | yes |
| Forward plan | yes |
| Non-goals | yes |

**Mismatches**

| # | Claim | Reality | Severity |
|---|-------|---------|----------|
| RM-1 | "Phase B — Foundation: ... **Secret vault** — AES-256-GCM encrypted store with scoped proxy tokens" (line 21) | The vault is in **TypeScript** (`packages/synapse-vault-mcp/src/vault.ts`). Listing it under the "Rust daemon" foundation phase implies the daemon ships an AES-256-GCM vault; it does not. | HIGH |
| RM-2 | "Phase D ... **5 adapters** — Identity registration, trust headers, vault integration, A2A signing" (line 36) | Every adapter is the same 25 lines. There is no per-tool integration. "5 adapters" should read "1 base adapter labelled 5 ways". | MEDIUM |
| RM-3 | "Phase D ... **Documentation** — README, ARCHITECTURE, TRUST_MODEL, PROTOCOL, ROADMAP" (line 41) | True. The ROADMAP doesn't list ARCHITECTURE/TRUST_MODEL as "stale" even though both pre-date the Phase D work. | LOW |
| RM-4 | "Non-Goals: ... **General-purpose AI agent framework** — Synapse provides identity and trust, not agent logic." (lines 80–82) | Strong, accurate framing. **Reuse this wording in the rewritten README.** | (positive) |

---

## docs/INSPIRATIONS.md

**State**

| Check | Result |
|-------|--------|
| Exists | yes |
| Non-empty | yes (4,570 B / 105 lines) |
| Identity / crypto inspirations | yes |
| Trust / reputation inspirations | yes |
| Vault / secret-mgmt inspirations | yes |
| Architecture inspirations | yes |
| "What Synapse is Not" closing | yes |

**Mismatches**

| # | Claim | Reality | Severity |
|---|-------|---------|----------|
| I-1 | "gRPC / Protocol Buffers — Synapse Protocol v1.0 uses a structured wire format (JSON-encoded, length-prefixed over Unix sockets) inspired by protobuf's message discipline." (lines 70–72) | The protocol is **newline-delimited JSON**, not length-prefixed. `daemon/src/ipc/mod.rs:55–74` uses `BufReader::read_line`. | MEDIUM |
| I-2 | "Microkernel / message-passing OS — The Synapse daemon is a small, privileged kernel. Everything else (adapters, MCP servers, CLI) runs as an untrusted satellite that communicates through the protocol." (lines 79–82) | The framing is aspirational. Currently the daemon's protocol only exposes **trust** ops — adapters/MCPs/CLI do not talk to the daemon at all in the demos. The "satellite" model is a future state. | MEDIUM |
| I-3 | "Sidecar proxy pattern (Envoy/Istio) — Adapters act as sidecars to their host tools." (lines 89–92) | No adapter runs as a sidecar process today. The adapters are imported as Python objects inside the host tool's Python process. Calling them "sidecars" overstates the architecture. | LOW |

Otherwise the document is well-curated and the closing "What Synapse Is Not" section is excellent positioning material.

---

## Pre-existing root audits (informational)

`BUG_REPORT.md`, `LAUNCH_BLOCKERS.md`, and `SECURITY_REVIEW.md` exist at the repo root and represent the previous audit pass. They are accurate inputs to this RC review. `LAUNCH_BLOCKERS.md` claims "**Real blockers: None.**" — this is **disputed by this audit**; see `RELEASE_SCORE.md` for the corrected position.

---

## Doc-level summary

| Doc | Verdict |
|-----|---------|
| `README.md` (root) | **REWRITE** — see `README_REWRITE.md` |
| `docs/ARCHITECTURE.md` | **REWRITE** — see `ARCHITECTURE_REALITY.md` for the corrected version |
| `docs/TRUST_MODEL.md` | **EDIT** — fix T-1, T-2, T-5 wording; keep the three-gate diagram |
| `docs/PROTOCOL.md` | **KEEP AS-IS** — the only fully accurate doc |
| `docs/ROADMAP.md` | **EDIT** — move RM-1 vault claim to its own line under Phase B as "TS package, not daemon"; clarify RM-2 |
| `docs/INSPIRATIONS.md` | **EDIT** — fix I-1, I-2, I-3; otherwise keep |
| `BUG_REPORT.md` | **KEEP** — historical record of Phase 4 fixes |
| `LAUNCH_BLOCKERS.md` | **UPDATE** — the "no blockers" claim is overruled by R-1, R-2, T-1, and the `npm install` failure; see `RELEASE_SCORE.md` |
| `SECURITY_REVIEW.md` | **KEEP + EXTEND** — `audit-rc/SECURITY_REVIEW.md` extends the original with the unfixed items still present in the tree |
