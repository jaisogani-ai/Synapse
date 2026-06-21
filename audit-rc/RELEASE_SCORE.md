# RELEASE_SCORE

**Date:** 2026-06-21
**Inputs:** `REPOSITORY_INVENTORY.md`, `LEGAL_AUDIT.md`, `DOC_AUDIT.md`,
`ARCHITECTURE_REALITY.md`, `SECURITY_REVIEW.md` (this RC pass), `GITHUB_REVIEW.md`.

Each dimension is scored on the basis of the working tree at this moment —
**not** what it could be after the launch-blocker fixes land. A second score
column ("After 75-min fixes") reflects the score immediately after the three
fixes called out in `GITHUB_REVIEW.md` § 6.

The scale: **0 = absent**, **5 = adequate**, **8 = strong**, **10 = exemplary**.

---

## Scores

| Dimension | Now | After 75-min fixes | Notes |
|-----------|-----|-------------------|-------|
| **Architecture** | **7.0** | 7.5 | Daemon is clean, idiomatic Rust. Capability code is orphaned. The two trust stores + two identity stores expose layering work that is not done yet. Diagram understates the system. |
| **Security** | **6.5** | 7.5 | Phase 4 closed every CRITICAL and most HIGHs. Remaining HIGHs (tamper-evident audit, signed trust file, identity-endpoint pinning, in-memory daemon) are documented and credible. Capability gate code-complete but unused is the weakest spot. |
| **Maintainability** | **7.0** | 7.5 | Many small files, clean module boundaries, idiomatic per-language. Spinout dilutes the picture; the `__main__` stub vs real `commands/` is the kind of split that confuses contributors. |
| **Documentation** | **6.5** | 8.0 | INSPIRATIONS and PROTOCOL are excellent; ROADMAP non-goals nail the framing. ARCHITECTURE is stale; README's "Phase D complete" is materially misleading given § 2a in `GITHUB_REVIEW.md`. The `README_REWRITE.md` here raises this to 8.0 alone. |
| **Developer Experience** | **5.0** | 7.0 | `npm install` fails. CLI prints `Stub:`. `cargo build` hard-codes the maintainer's path. Marquee demo uses a simulated vault. Each fix is small, but all four are on the first 5 minutes of a contributor's journey. |
| **Launch Readiness** | **5.5** | 8.0 | Code is real, tests pass, license is clean. The three blockers in § "Launch blockers" below are the gap between "ready" and "not ready". |
| **Originality** | **7.5** | 7.5 | The problem statement and reputation-as-primitive framing are fresh. Cryptography is textbook (rightly so). Capability registry with risk levels is a small but original touch. |

**Overall (unweighted mean):** **6.4 now → 7.6 after 75-min fixes.**

Personal read: the work is one ordered checklist away from being something
people will actually star. The checklist is short and known.

---

## Launch blockers (mandatory, in priority order)

These three close 80% of the gap. Total estimated effort: **~75 minutes**.

### B-1 — Wire the CLI (~60 min) — **REQUIRED**
**File:** `packages/synapse-cli/synapse_cli/__main__.py`

Currently a stub that prints `Stub: would send task…`. Real implementations
exist in `commands/send_task.py` (225 LOC) and `commands/inbox.py` (202 LOC)
but are not reachable. Without this, `synapse send-task` and `synapse inbox`
do nothing. **The published CLI does not work end-to-end.**

Acceptance: `python -m synapse_cli send-task --from a --to b --task "hello"`
makes a real signed HTTP POST to the resolved endpoint.

### B-2 — Fix `package.json` workspaces (~5 min) — **REQUIRED**
**File:** `package.json`

Remove `packages/synapse-trust-mcp` (directory empty) and `packages/synapse-cli`
(Python, no `package.json`) from the `workspaces` array. Then `rm -rf packages/synapse-trust-mcp`.

Acceptance: `npm install` from repo root succeeds.

### B-3 — Be honest about the demo (~10 min) — **STRONGLY RECOMMENDED**
**File:** `examples/vps-handoff-no-raw-keys/README.md` (and ideally `demo.py`)

Either rewrite the demo to spawn the real TS vault MCP, or update the README to
say: "This demo uses a simulated vault in-process to keep the script
self-contained. The cryptographic vault under test lives in
`packages/synapse-vault-mcp` — see its `test/vault.test.ts`." Pick one.

Acceptance: a reader cannot fairly accuse the project of misrepresenting the
vault.

---

## Strongly recommended (not blockers, but visible)

### S-1 — Trim the daemon banner and `health` subsystem list
**File:** `daemon/src/main.rs:64–70`, `daemon/src/ipc/mod.rs:120–127`

Replace `["identity", "vault", "trust", "a2a"]` with `["trust"]`. Then **delete**
the empty `daemon/src/{identity,vault,a2a_signer}/` directories. They make the
repo look mid-refactor for no reason.

### S-2 — Fix `cargo build` invocation in README
Drop the `~/.cargo/bin/` prefix; trust PATH.

### S-3 — Remove the "T8 reputation memory" comment
`daemon/src/trust/reputation.rs:77` — cosmetic remnant of the v0 architecture.
30 seconds. (Flagged as L-1 in `BUG_REPORT.md`, still present.)

### S-4 — Decide what to do with `spinout/`
Either: (a) carve it out into separate repos before launch; or (b) write a
sharper `spinout/README.md` saying "these will be moved to their own repos
by <date>" and link to issues tracking each move. Either signals intent;
the current one-line note does not.

### S-5 — Apply the README rewrite
Drop in `audit-rc/README_REWRITE.md`. The current README's "Phase D complete"
+ the empty `daemon/src/identity/vault/a2a_signer/` directories in the tree
listing is the single most attackable doc surface.

### S-6 — Apply the architecture rewrite
Replace `docs/ARCHITECTURE.md` with `audit-rc/ARCHITECTURE_REALITY.md`. The
current ARCHITECTURE.md describes a Phase B architecture that no longer
exists in this form.

---

## What can ship as-is

- The Apache 2.0 + NOTICE + SPDX headers. Done.
- The Rust daemon's trust store, protocol, IPC, capability module (with the
  caveat that capability is unwired).
- The Python `synapse-core` SDK in full.
- The TypeScript `synapse-vault-mcp` in full.
- The CLI's real implementations in `commands/`.
- The 3 demos themselves (caveat: vps-handoff messaging per B-3).
- `docs/PROTOCOL.md`, `docs/INSPIRATIONS.md`, `docs/ROADMAP.md` (with minor
  edits per `DOC_AUDIT.md` RM-1, I-1, I-2).

---

## Final verdict

> **Not ready today. Ready in 75 minutes.**

The audit found no architectural rework required, no security CRITICAL
unfixed, no licence issue. The gap between the current state and a launch-
worthy state is composed of small, surgical edits that the existing
codebase already supports:

1. **Wire one Python entry point.**
2. **Delete two `package.json` lines and one empty directory.**
3. **Rewrite one demo paragraph or one demo file.**

After those three, drop in the rewritten README and ARCHITECTURE_REALITY,
and Synapse is something serious people will read, star, and consider
adopting. The work that earned this readiness is real. The remaining
distance is not.
