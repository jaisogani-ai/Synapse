# REPOSITORY_INVENTORY

**Date:** 2026-06-21
**Method:** Walked the working tree, counted real source files (excluding `target/`, `__pycache__/`, `.pytest_cache/`), and read each top-level subsystem.

Reality vs. documentation flags appear under each subsystem.

---

## 1. Rust daemon — `daemon/`

| Item | Reality |
|------|---------|
| Crate | `synapse-daemon` (lib `synapse_daemon`, bin `synapsed`) |
| Source files | 6 (`main.rs`, `lib.rs`, `protocol/mod.rs`, `ipc/mod.rs`, `trust/mod.rs`, `trust/reputation.rs`, `security/capability.rs`, `security/mod.rs`) |
| Integration tests | 4 (`engine.rs`, `ipc_socket.rs`, `protocol.rs`, `trust_reputation.rs`) |
| Total LOC | ~1,544 |
| State store | `TrustStore::new_in_memory()` — **SQLite `:memory:`**, no on-disk persistence |
| Empty directories | `daemon/src/a2a_signer/`, `daemon/src/identity/`, `daemon/src/vault/` — zero files inside, all three created `Jun 20 18:36` |
| Status | Active — boots, serves protocol, all subsystems compile |
| Owner | core |

**Subsystems actually implemented:**

| Module | Purpose | Status |
|--------|---------|--------|
| `protocol` | Synapse Protocol v1.0 envelope, TrustOp tagged union, JSON codec | Active |
| `ipc` | Tokio Unix-socket server, dispatch loop | Active |
| `trust::reputation` | SQLite-backed `ReputationMemory`, confidence-weighted scoring | Active |
| `security::capability` | `CapabilityPolicy` (fs/shell/net policy from caps) | **Orphaned** — defined but never called from `ipc` or `main` |

**Banner claims "subsystems: identity, vault, trust, a2a".** Reality: only `trust` exists. The other three are advertised in `health` responses and `print_banner` but have no code behind them.

---

## 2. Python core SDK — `packages/synapse-core/`

| Module | Purpose | LOC | Status |
|--------|---------|-----|--------|
| `synapse/security/zero_trust.py` | HS256 JWT issuance + HMAC-SHA256 request signing | 251 | Active |
| `synapse/security/capabilities.py` | Capability registry, `CapabilitySet`, wildcard matcher | 152 | Active |
| `synapse/security/secret_detector.py` | 140+ secret patterns + Shannon-entropy fallback | 294 | Active |
| `synapse/security/supply_chain.py` | OSV.dev lookup + entropy heuristics | 209 | Active |
| `synapse/core/__init__.py` | Empty re-export shell | 14 | Active |

Owner package: `synapse-core` (pyproject.toml).
All four security modules are dependency-free Python stdlib.

---

## 3. Python CLI — `packages/synapse-cli/`

| Module | Purpose | LOC | Status |
|--------|---------|-----|--------|
| `__main__.py` | Argparse entry point | 41 | **STUB** — prints `"Stub: would send..."` (M-6 in `BUG_REPORT.md`, deferred) |
| `commands/send_task.py` | Real send-task implementation | 225 | Active but **unreachable** via CLI |
| `commands/inbox.py` | Real inbox accept/reject/list | 202 | Active but **unreachable** via CLI |
| `a2a.py` | A2A spec types (Task, Message, Part, Artifact) | 188 | Active |
| `a2a_signer.py` | HMAC-signed payloads with timestamp binding | 76 | Active (replay-safe after Phase 4 fix) |
| `receiver.py` | A2A JSON-RPC receiver with replay/signature gates | 212 | Active |
| `transport.py` | HTTP transport, 12 MiB body cap | 174 | Active |
| `inbox_store.py` | SQLite pending-tasks queue | 123 | Active |
| `identity_resolver.py` | JSON-file agent_id → URL registry | 48 | Active |
| `trust.py` | JSON-file score store (0.0–1.0) | 61 | Active |
| `vault_client.py` | In-memory plaintext secret/proxy store | 74 | Active — **plaintext, divergent from TS vault** |
| `audit.py` | JSONL audit log | 59 | Active |

Two stores live in JSON files (`trust.py`, `identity_resolver.py`) — neither authenticated. Daemon never writes to them; CLI is sole owner.

---

## 4. Tool adapters — `packages/adapters/`

| Adapter | Purpose | LOC | Status |
|---------|---------|-----|--------|
| `base.py` | Shared identity/signing/vault logic | 202 | Active |
| `claude_code/` | Subclass setting `tool_type = "claude-code"` | 24+101 | Active stub |
| `cursor/` | Subclass | 24+79 | Active stub |
| `codex/` | Subclass | 24+79 | Active stub |
| `vscode/` | Subclass | 24+79 | Active stub |
| `antigravity/` | Subclass | 24+81 | Active stub |

Every adapter is a 25-line subclass that sets `tool_type`. No tool-specific integration; behaviour is 100% in `BaseAdapter`. The "5 adapters" framing in README is technically true but functionally one adapter with five labels.

---

## 5. TypeScript MCP — `packages/synapse-vault-mcp/`

| File | Purpose | LOC | Status |
|------|---------|-----|--------|
| `src/vault.ts` | AES-256-GCM `SecretVault` + 8 exposure regexes | 230 | Active — only Node `node:crypto` |
| `src/server.ts` | MCP tool registration (6 tools) | 102 | Active |
| `src/index.ts` | Entry shim | 16 | Active |
| `test/vault.test.ts` | Vault unit tests | 132 | Active |

Owner package: `@synapse/vault-mcp`.
Master key generated per-process when none provided (SL-1).

---

## 6. Empty workspace stub — `packages/synapse-trust-mcp/`

Directory exists with **no files**. `package.json` declares it as an npm workspace target (line 14). **`npm install` from the repo root will fail** ("No matching workspace for synapse-trust-mcp").

Owner: nominal. Should be deleted from the workspaces list, or fleshed out.

---

## 7. Tests

| Location | Files | Tests | Reality |
|----------|-------|-------|---------|
| Rust integration | `daemon/tests/*.rs` | 4 files (engine, ipc_socket, protocol, trust_reputation) | Active |
| Rust unit | inline `#[cfg(test)]` modules | Multiple | Active (5 in protocol, 7 in capability, 7 in reputation, 5 in ipc) |
| Python SDK | `tests/unit/` | 4 files (capabilities, secret_detector, supply_chain, zero_trust) | Active |
| Python CLI | `packages/synapse-cli/tests/test_a2a_delegation.py` | 1 file, 369 LOC | Active |
| Adapter | `packages/adapters/*/test_adapter.py` | 5 files | Active |
| TS vault | `packages/synapse-vault-mcp/test/vault.test.ts` | 1 file | Active |

README claim **"72 tests"** is not independently verified here, but the test file count and structure are real.

---

## 8. Examples — `examples/`

| Example | Files | Reality |
|---------|-------|---------|
| `vps-handoff-no-raw-keys/` | `demo.py` (320 LOC) + 754 KB `demo.gif` + 600 B `demo.tape` | Demo uses an **inline simulated vault**, not `packages/synapse-vault-mcp`. The TS vault is never exercised by demos. |
| `malicious-sender-rejection/` | `demo.py` (343 LOC) | Active |
| `cross-device-task-delegation/` | `run_vps.py` + `run_laptop.py` + `shared_setup.py` (304 LOC total) | Active — two-terminal demo |

All three rely on `sys.path.insert(...)` hacks — they run from the repo root without `pip install -e .`, and break otherwise.

---

## 9. Spinout — `spinout/`

`spinout/README.md` contents in full:

> These modules were part of Synapse v0 and have genuine standalone value but are out of scope for the v1 trust layer. Each could become its own repo.

| Subdir | Reality |
|--------|---------|
| `synapse-memory-mcp/` | 5 TS files (~336 LOC), context-pack memory protocol |
| `synapse-context-mcp/` | 4 TS files (~368 LOC), context compression |
| `synapse-skills-mcp/` | 4 TS files (~461 LOC), skill registry |
| `synapse-backend-architect-mcp/` | 10 TS files (~1,659 LOC) — by far the largest single package in the repo |
| `synapse-router/` | 3 Python files (~267 LOC) — cost/routing |
| `security-workers/compliance/india-compliance/` | 1 Python file (161 LOC) |

**Status:** Out of scope for v1. Documented as such in `ROADMAP.md` non-goals and `spinout/README.md`. Total **~3,400 LOC sitting in the v1 repo with no role in v1**. Hacker News will ask why this is here.

---

## 10. Documentation — `docs/` + root

| File | Status |
|------|--------|
| `README.md` (root) | Recently re-written, accurate apart from items flagged in `DOC_AUDIT.md` |
| `docs/ARCHITECTURE.md` | **Stale** — claims "Phase B" but ROADMAP is on "Phase D" |
| `docs/TRUST_MODEL.md` | Accurate for the model; misleading about where some pieces live |
| `docs/PROTOCOL.md` | Accurate — matches `daemon/src/protocol/mod.rs` 1:1 |
| `docs/ROADMAP.md` | Accurate for what was attempted; claims "Secret vault" as Phase B but the vault is TS in `packages/synapse-vault-mcp` |
| `docs/INSPIRATIONS.md` | Solid — well-curated influences, no factual issues |
| `BUG_REPORT.md` (root) | Previously generated audit. Inputs to this report. |
| `LAUNCH_BLOCKERS.md` (root) | Previously generated. **Optimistic** — see `DOC_AUDIT.md` for what it omits. |
| `SECURITY_REVIEW.md` (root) | Previously generated. Inputs to this report. |
| `LEGAL_AUDIT.md` (this audit) | New |

---

## 11. Manifests

| File | License declared | Workspace declares missing dirs? |
|------|-----------------|-------------------------------------|
| `Cargo.toml` (workspace) | `Apache-2.0` | `members = ["daemon"]` — clean |
| `daemon/Cargo.toml` | inherits | n/a |
| `pyproject.toml` (root) | `Apache-2.0` | `pythonpath` includes `packages/synapse-cli` — fine |
| `packages/synapse-core/pyproject.toml` | `Apache-2.0` | n/a |
| `packages/synapse-cli/pyproject.toml` | `Apache-2.0` | n/a |
| `spinout/synapse-router/pyproject.toml` | `Apache-2.0` | n/a |
| `package.json` (root) | `Apache-2.0` | **`packages/synapse-trust-mcp` (empty)** and **`packages/synapse-cli` (Python, no package.json)** declared as workspaces — both will break `npm install` |
| `packages/synapse-vault-mcp/package.json` | `Apache-2.0` | clean |
| `spinout/**/package.json` (5 of them) | `Apache-2.0` | n/a |

---

## Summary table — by subsystem

| Subsystem | Purpose | Status | Owner package | Active/Deprecated |
|-----------|---------|--------|---------------|--------------------|
| Daemon trust | Reputation scoring | Live (in-memory only) | `synapse-daemon` | Active |
| Daemon protocol | Wire format | Live | `synapse-daemon` | Active |
| Daemon IPC | Unix socket | Live | `synapse-daemon` | Active |
| Daemon capability policy | fs/shell/net policy | Code-complete but **uncalled** | `synapse-daemon` | Active-dormant |
| Daemon identity/vault/a2a | Advertised in banner | **Empty directories** | `synapse-daemon` | **Vapor** |
| Python zero-trust | JWT + HMAC | Live | `synapse-core` | Active |
| Python capabilities | Cap registry | Live | `synapse-core` | Active |
| Python secret detector | 140+ patterns | Live | `synapse-core` | Active |
| Python supply chain | OSV + entropy | Live | `synapse-core` | Active |
| Python CLI argparse | User-facing CLI | **Stub** | `synapse-cli` | Active-stub |
| Python CLI send_task / inbox | Real command logic | Live but **not wired to CLI** | `synapse-cli` | Active-orphan |
| Python A2A signer/receiver/transport | HTTP A2A | Live | `synapse-cli` | Active |
| Python inbox SQLite | Task queue | Live | `synapse-cli` | Active |
| Python trust.json / identity.json | Score + endpoint registry | Live, **unauthenticated** | `synapse-cli` | Active |
| Python vault_client | Local proxy mirror | Live, **plaintext** | `synapse-cli` | Active |
| TS vault MCP | AES-256-GCM vault | Live | `synapse-vault-mcp` | Active |
| TS trust MCP | Advertised in `package.json` workspaces | **Empty directory** | `synapse-trust-mcp` | **Vapor** |
| 5 adapters | Tool integrations | 25-line stubs over `BaseAdapter` | `adapters` | Active-thin |
| 3 demos | Launch demos | Run; vps-demo simulates vault | `examples` | Active |
| Spinout (6 packages) | v0 leftovers | Out of scope per docs | `spinout` | **Deprecated-in-repo** |
