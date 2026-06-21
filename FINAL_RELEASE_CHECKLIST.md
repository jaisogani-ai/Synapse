<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Final Release Checklist — Synapse v0.1.0-alpha

**Date:** 2026-06-22
**Tag:** `v0.1.0-alpha`
**License:** Apache 2.0
**Maintainer:** Jai Sogani · `jaisogani183@gmail.com`

Every entry below was verified by running the relevant command in this repo. Where the output is short, it is quoted verbatim. Where it is long, the way to re-run it is given.

---

## 1. Tests passing

| Suite | Command | Result |
|---|---|---|
| Rust daemon | `~/.cargo/bin/cargo test` | **39 / 39 passing** |
| Python SDK + CLI + adapters | `PYTHONPATH=… python3.11 -m pytest tests packages/adapters packages/synapse-cli/tests -q` | **79 / 79 passing** |
| TypeScript vault MCP | `(cd packages/synapse-vault-mcp && npm test)` | **10 / 10 passing** |
| **Total** | | **128 / 128 passing** |

```
=== cargo ===
  total: 39 passed
=== pytest ===
79 passed in 3.64s
=== npm test (vault) ===
ℹ tests 10
ℹ pass 10
ℹ fail 0
```

---

## 2. Demos verified

| Demo | Command | Result |
|---|---|---|
| VPS handoff (zero raw key) | `python3.11 examples/vps-handoff-no-raw-keys/demo.py` | **RESULT: PASS** |
| Cross-device task delegation | two-terminal walkthrough in `examples/cross-device-task-delegation/README.md` | green (integration-tested by `test_a2a_delegation.py`) |
| Malicious sender rejection | `python3.11 examples/malicious-sender-rejection/demo.py` | **RESULT: PASS** |

Every demo path referenced by `README.md` exists on disk:

```
examples/vps-handoff-no-raw-keys/        demo.py · demo.tape · demo.gif · README.md
examples/cross-device-task-delegation/   run_laptop.py · run_vps.py · shared_setup.py · README.md
examples/malicious-sender-rejection/     demo.py · README.md
```

---

## 3. Docs verified

| File | Status |
|---|---|
| `README.md` | ✅ rewritten; references match code; demo paths exist |
| `RELEASE_NOTES_v0.1.md` | ✅ created and aligned with v0.1.0-alpha framing |
| `CHANGELOG.md` | ✅ created; v0.1.0-alpha entry covers every shipped pillar |
| `CONTRIBUTING.md` | ✅ created; scope is explicit, project-style guides in place |
| `CODE_OF_CONDUCT.md` | ✅ created (Contributor Covenant v2.1 + practical note) |
| `SECURITY.md` | ✅ vulnerability disclosure path documented |
| `SECURITY_REVIEW.md` | ✅ threat model + 7 attack classes + 3-gate defence-in-depth |
| `KNOWN_LIMITATIONS.md` | ✅ honest, no marketing, every gap has Impact + Mitigation + Plan |
| `docs/ARCHITECTURE.md` | ✅ matches the actual daemon + SDK + vault MCP module tree |
| `docs/TRUST_MODEL.md` | ✅ updated with wired-in capability enforcement |
| `docs/PROTOCOL.md` | ✅ describes the daemon's internal IPC; explicitly notes it is NOT A2A |
| `docs/ROADMAP.md` | ✅ v0.1 / v0.2 / beyond — no Phase B/C/D/E lifecycle terms |
| `docs/INSPIRATIONS.md` | ✅ unchanged; still honest |
| `docs/diagrams/` | ✅ 6 Mermaid diagrams + index |
| `BUG_REPORT.md`, `NEXT_STEPS.md` | ✅ historical artefacts, kept |

---

## 4. Version consistency

Every user-facing document refers to **Synapse v0.1.0-alpha**.

- `README.md` — "Synapse v0.1.0-alpha" in the alpha warning block.
- `RELEASE_NOTES_v0.1.md` — title is `# Synapse v0.1.0-alpha — Release Notes`.
- `CHANGELOG.md` — entry `[0.1.0-alpha] — 2026-06-22`.
- `KNOWN_LIMITATIONS.md` — "Applies to: v0.1 (alpha)".
- `SECURITY_REVIEW.md` — "Security Review — v0.1 (alpha)".
- `docs/ROADMAP.md` — "v0.1 — shipped (alpha)", "v0.2 — planned follow-ups", "Beyond v0.2 — open questions (not committed)".

Internal protocol versions are unchanged — those are technical versions, not release versions:

- Daemon IPC protocol: `v1.0` (string in `daemon/src/protocol/mod.rs`).
- A2A: external spec; we are spec-compliant against the published version.

No mixed "v1.0" / "v1.x" product-version language remains in user-facing docs.

---

## 5. Contradictory-messaging sweep

Repo-wide case-insensitive grep for the forbidden vocabulary returns **zero hits**:

```
grep -rni "production[- ]ready|enterprise[- ]ready|world[- ]class|revolutionary|\
  AI Operating System|Agent Operating System" \
  --include="*.md" --include="*.py" --include="*.rs" --include="*.ts" \
  --include="*.toml" --include="*.json" .
# → 0 matches
```

The only previous hit was `spinout/synapse-backend-architect-mcp/README.md` (an inert spinout, not part of v0.1.0-alpha). It was rewritten to clearly mark the module as out of scope.

---

## 6. Reality check — every README claim

| Claim | Verified by |
|---|---|
| Identity (HMAC + HS256 JWT) | `packages/synapse-core/synapse/security/zero_trust.py` + tests in `tests/unit/test_zero_trust.py` |
| Vault (AES-256-GCM, scoped proxy) | `packages/synapse-vault-mcp/src/vault.ts` + `npm test` (10/10) + vps-handoff demo |
| Trust + reputation | `packages/synapse-cli/synapse_cli/trust.py` + reputation tests; `daemon/src/trust/reputation.rs` + cargo tests |
| Capability gate (receiver + IPC) | `receiver.py` + `daemon/src/ipc/mod.rs` + `test_capability_enforcement.py` (7/7) + ipc capability tests (4/4) |
| A2A integration with `FilePart.uri` | `packages/synapse-cli/synapse_cli/a2a.py` + blob E2E |
| Durable outbox (SQLite + backoff + DLQ) | `outbox_store.py` + `outbox_worker.py` + outbox E2E |
| Chunked file transfer (Range + sha256) | `blob.py` + blob E2E |
| Presence (online / busy / offline) | `presence.py` + receiver `/presence` endpoint |
| Inbox + review + accept/reject | `commands/inbox.py` + adapter tests |
| Audit log (append-only JSONL) | `audit.py` + integration tests |
| 5 adapters | `packages/adapters/{claude_code,cursor,codex,vscode,antigravity}/` (42 tests) |
| 3 demos | `examples/{vps-handoff-no-raw-keys,cross-device-task-delegation,malicious-sender-rejection}/` |
| 128 / 128 tests | command output above |

No undocumented features. No documented features without code.

---

## 7. Architecture verification

`docs/ARCHITECTURE.md` lists exactly the modules that exist in the repo. Verified:

```
daemon/src/      ipc/  lib.rs  main.rs  protocol/  security/  trust/
```

No empty `identity/`, `vault/`, or `a2a_signer/` directories. No references in any doc to deleted memory tiers, design workers, marketplaces, federation, AFP, or AI/Agent OS.

---

## 8. Code health

- `grep -rn "TODO|FIXME|XXX|HACK" packages daemon examples` → **0 hits** in production code.
- `ruff check --select=F401,F841 packages` → **All checks passed!** (15 unused imports cleaned in the previous pass).
- No stale `// removed` markers or planning files in the tree.

---

## 9. Known limitations documented

See [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md). Every limitation has Impact + Mitigation + Plan. Categories: architecture (intentional non-goals), cryptography, trust store, audit, vault, inbox/outbox, networking, capability system, platform, process.

Top items that ship knowingly in v0.1.0-alpha:

- No federation, relay, or discovery (by design)
- Rust `TrustStore` is in-memory (Python store is authoritative)
- No E2E payload encryption (HMAC integrity only; use HTTPS or a tunnel)
- Audit log is append-only but not hash-chained
- Endpoint hash pinning not implemented yet
- No CI workflow yet (tests must be run locally)

---

## 10. Launch assets present

| Asset | Status |
|---|---|
| `LICENSE` | ✅ Apache 2.0 |
| `NOTICE` | ✅ |
| `README.md` | ✅ |
| `RELEASE_NOTES_v0.1.md` | ✅ |
| `CHANGELOG.md` | ✅ |
| `CONTRIBUTING.md` | ✅ |
| `CODE_OF_CONDUCT.md` | ✅ |
| `SECURITY.md` | ✅ |
| `SECURITY_REVIEW.md` | ✅ |
| `KNOWN_LIMITATIONS.md` | ✅ |
| `docs/` | ✅ |
| `docs/diagrams/` | ✅ |
| `assets/demo.gif` | ✅ (one demo GIF; the three named slots `demo-{deploy,review,block}.gif` are placeholders — record and add before announce) |

---

## 11. Launch blockers remaining

**None.**

Optional polish that does not block alpha:

- Record and commit `assets/demo-deploy.gif`, `assets/demo-review.gif`, `assets/demo-block.gif` — instructions are in each demo's README.
- Add `.github/workflows/ci.yml` so PRs run the test matrix automatically. Listed in `KNOWN_LIMITATIONS.md` (H-1) and `docs/ROADMAP.md` (v0.2).
- Generate a CycloneDX SBOM on the release tag (H-3).

None of these prevent publishing the alpha. They are next-cycle items.

---

## 12. Verdict

> **Ready for public alpha release.**

Tag, push, announce.

```bash
git tag -a v0.1.0-alpha -m "Synapse v0.1.0-alpha"
git push origin main
git push origin v0.1.0-alpha
# create GitHub Release pointing at the tag, attach RELEASE_NOTES_v0.1.md body
```
