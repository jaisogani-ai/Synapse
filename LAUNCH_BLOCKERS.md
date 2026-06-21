# Synapse v1 — Launch Blockers

**Date:** 2026-06-21
**Regenerated from scratch.** Old "all clean, 72/72" report is superseded
by the `audit-rc/` audit and this reconciliation pass.

Every status below was verified by running the relevant command in this
session and observing its real output. Items I did not run end-to-end are
listed explicitly as "documented gap" rather than "fixed."

---

## P0 — closed in this pass

| # | Item | How verified |
|---|------|--------------|
| P0-1 | Project named `synapse` everywhere; old marketing name fully purged | Repo-wide case-insensitive grep for the old marketing slug returned 0 hits. `package.json` `name: "synapse"`, `pyproject.toml` `name = "synapse"`, `Cargo.toml` workspace package config — all match. |
| P0-2 | CLI wired to real `commands/send_task.py` and `commands/inbox.py` | Replaced stub `__main__.py`. Live end-to-end run drove `ZeroTrustNetwork → A2ASigner → IdentityResolver → A2AServer (real receiver) → InboxStore → CLI inbox list`. The `synapse inbox list` subprocess returned the real submitted task with the actual `task_id`, `sender=alice`, `sender_score=0.9`, `preview="hello bob"`. |
| P0-3 | `package.json` workspaces fixed; `npm install` succeeds | Removed `packages/synapse-trust-mcp` (empty dir, also `rmdir`'d) and `packages/synapse-cli` (Python) from workspaces. Fixed `~/.cargo/bin/cargo` → `cargo`. `npm install` from repo root: **added 99 packages, 0 vulnerabilities**. |
| P0-4 | vps-handoff demo uses real AES-256-GCM `SecretVault` | Replaced the inline `DemoVault` with `RealVault`, a Python facade over a new Node bridge (`packages/synapse-vault-mcp/src/bridge.ts` → `dist/bridge.js`) that drives the actual `SecretVault` class. End-to-end run: `RESULT: PASS`. Demo asserts `resolved == real_api_key` after the proxy resolves through the Node child — proving the real AES-256-GCM encrypt → decrypt path ran. The vault's `audit_log` is fetched **from the Node process**. |
| P0-5 | A2A claims corrected in README + ARCHITECTURE | README's pillar table now says A2A lives in `packages/synapse-cli/synapse_cli/a2a.py`. README architecture section and `docs/ARCHITECTURE.md` carry the verbatim user-supplied disclaimer about daemon IPC vs A2A. ARCHITECTURE's "A2A Integration" pillar is rewritten to point to the Python A2A files and explicitly warns that `daemon/src/protocol/` is **not** A2A. |
| P0-6 | Daemon banner/health only lists implemented subsystems | `daemon/src/main.rs` banner now logs `subsystems: trust`. `daemon/src/ipc/mod.rs` `/health` returns `subsystems: ["trust"]`. The accompanying unit test now asserts identity/vault/a2a are **not** in the list. `cargo build` succeeds; `cargo test` passes **35 tests** (24 lib + 2 engine + 2 ipc_socket + 4 protocol + 3 trust_reputation). Empty `daemon/src/{identity,vault,a2a_signer}/` directories deleted. ROADMAP.md lists "Rust-native identity / vault / a2a-signer modules" as a P1 follow-up. |

## P1 — done in this pass

| # | Item | What was done |
|---|------|---------------|
| P1-7 | Capability enforcement | Wiring `daemon/src/security/capability.rs` into the IPC dispatcher requires per-request caller authentication on the Unix socket, which the current internal IPC protocol does not carry — too large for this pass. Per the user's explicit instruction, the gap is now loudly documented at the bottom of the "Gate 3: Capability Authorization" section of `docs/TRUST_MODEL.md`: "Do not rely on Rust-side capability enforcement for untrusted multi-user deployments in v1." ROADMAP.md lists wiring as a P1 follow-up. |
| P1-8 | Dual trust/identity stores reconciled | Picked the Python store under `packages/synapse-cli/synapse_cli/trust.py` (and `packages/synapse-core/synapse/security/`) as **v1-authoritative**. Updated `docs/TRUST_MODEL.md` and `docs/ARCHITECTURE.md` (new "Authoritative stores (v1)" section) to say this explicitly. The Rust store is documented as the future-native target, not a current source of truth. |
| P1-9 | Trust persistence | Chose path (b) — fix the docs. `docs/TRUST_MODEL.md`, `docs/ARCHITECTURE.md`, and `docs/ROADMAP.md` no longer claim "SQLite-backed" for the Rust trust store; they say "in-memory in v1" and list SQLite persistence as a P1 follow-up. |

## Part 2 — README visual assets

| Item | What was done |
|------|---------------|
| Demo GIF | Rerecorded `assets/demo.gif` (606 KB) using `vhs` against the rewired `examples/vps-handoff-no-raw-keys/demo.py`. The GIF now shows the **real** AES-256-GCM vault path. README references it as `![Synapse demo](assets/demo.gif)` (relative path, renders on GitHub). |
| Badges | The three existing badges (License, Daemon, SDK) are static shields linking to real paths (`LICENSE`, `daemon/`, `packages/synapse-core/`). No CI badge — there is no `.github/workflows/` directory, so none was added. Nothing to remove. |

---

## Real verification commands (re-runnable)

```
# from repo root /Users/jaisogani/Synapse/synapse

# 1. Rename audit
grep -ri "<old-marketing-slug>" .                # → 0 hits

# 2. CLI works
SYNAPSE_HOME=/tmp/x python3.11 -m synapse_cli send-task \
  --from alice --to bob --task "hello"           # → real signed flow, JSON output

# 3. npm install succeeds
npm install                                      # → added 99 packages, 0 vulns

# 4. Real-vault demo
python3.11 examples/vps-handoff-no-raw-keys/demo.py   # → RESULT: PASS

# 5. Daemon banner / health
~/.cargo/bin/cargo test                          # → 35 tests pass; health asserts only "trust"
```

---

## Remaining items (NOT blockers — for the next pass)

These are honest follow-ups, not "None":

1. **Wire `daemon/src/security/capability.rs` into IPC dispatch** — requires
   per-request caller auth on the Unix socket. P1.
2. **Persist `daemon/src/trust/reputation.rs` to SQLite.** Currently
   in-memory; documented as such, but a restart loses every recorded
   outcome.
3. **Reconcile / collapse the dual trust + identity stores.** Pick Python
   as authoritative (already documented). The medium-term goal is to move
   the canonical stores into Rust; until then, the Rust store is a stub.
4. **Rust-native identity / vault / a2a-signer.** Today this logic lives
   in the Python SDK and the TS vault MCP. Listed in ROADMAP.md.
5. **Carryovers from the prior MEDIUM/LOW list** that were not in scope
   here — inbox SQLite WAL + busy timeout (M-1), per-sender rate limit
   (M-2), secret-detector pass over audit `detail` (M-3), vault_client
   AES-at-rest (M-7), audit tamper-evidence (M-9), identity_resolver
   endpoint hash pinning (SH-3), and the L-1/L-2 cosmetics. None of these
   block launch; all are tracked in the previous LAUNCH_BLOCKERS history
   and BUG_REPORT.md.
