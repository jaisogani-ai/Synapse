<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Documentation Audit — v1.0 launch

**Date:** 2026-06-21
**Scope:** Every Markdown file at the repo root, in `docs/`, and in
`examples/*/`. Per-file disposition: **KEEP**, **REWRITE**, **REMOVE**, or
**MISSING (create)**.

---

## Verdict at a glance

| File | Disposition | One-line reason |
|---|---|---|
| `README.md` | **REWRITE** | Stale "v1 release candidate" status; no demo screenshots/GIFs; no feature comparison table; no Quick Start that walks an outsider through install → first task. |
| `LICENSE` | **KEEP** | Apache-2.0, unmodified. |
| `NOTICE` | **KEEP** | Correct, complete. |
| `docs/ARCHITECTURE.md` | **KEEP w/ minor edits** | Accurate after the v1.0.1 capability rewrite. Add the outbox + blob + presence modules to the inventory; refresh threading-model bullet to match the worker. |
| `docs/TRUST_MODEL.md` | **KEEP** | Updated in v1.0.1 capability pass — Gate 3 wiring documented. |
| `docs/PROTOCOL.md` | **REWRITE** | Missing the new `caps` envelope field and `capability_denied` error code; missing the A2A method → required capability table. |
| `docs/ROADMAP.md` | **REWRITE** | Uses internal "Phase B/C/D/E" lifecycle terms that don't help a launch reader. Some completed work is duplicated; some future work is too speculative for v1. |
| `docs/INSPIRATIONS.md` | **KEEP** | Honest, useful colour for HN readers. No stale architecture inside. |
| `BUG_REPORT.md` | **KEEP** | Historical artefact of Phase 4 closure pass. Linked from launch docs. |
| `LAUNCH_BLOCKERS.md` | **KEEP** | Superseded by `NEXT_STEPS.md` for v1.0 but cheap to keep as history; "Real blockers: None" entry is correct. |
| `NEXT_STEPS.md` | **KEEP** | Authoritative status doc for v1.0. Updated by v1.0.1 capability pass. |
| `SECURITY_REVIEW.md` (root, legacy) | **REWRITE** | Phase 4 snapshot. Will be superseded by `SECURITY_REVIEW.md` (rewritten in Phase 3) and a new `KNOWN_LIMITATIONS.md`. |
| `audit-rc/*.md` (8 files) | **KEEP** | Audit history; useful for credibility. Add a one-line note at top of `audit-rc/README.md` saying these reports were the basis for v1.0 reconciliation. |
| `examples/vps-handoff-no-raw-keys/README.md` | **REWRITE** | Was the marquee demo before the real-vault rewire; now should describe the actual Node-bridge-driven AES-256-GCM path. |
| `examples/cross-device-task-delegation/README.md` | **KEEP w/ minor edits** | Mostly accurate; remove "(no offline queue)" line (outbox now exists) and note where capability gate fires. |
| `examples/malicious-sender-rejection/README.md` | **REWRITE** | Demo predates outbox + capability enforcement. Add a third attack vector: insufficient capability. |
| `docs/diagrams/` | **MISSING (create)** | No diagrams exist. Phase 4 will create 6 Mermaid diagrams. |
| `SECURITY.md` (root) | **MISSING (create)** | No vulnerability-reporting policy. Phase 3 creates. |
| `KNOWN_LIMITATIONS.md` (root) | **MISSING (create)** | Phase 3 creates. |
| `FINAL_LAUNCH_REPORT.md` (root) | **MISSING (create)** | Phase 6 creates. |
| `docs/DOC_AUDIT_REPORT.md` | **CREATED** | This file. |

---

## Stale references found (and where)

Repo-wide greps for the forbidden vocabulary list:

| Pattern | Files | Action |
|---|---|---|
| `Phase B` / `Phase C` / `Phase D` / `Phase E` | `docs/ROADMAP.md` only | Rewrite roadmap to use feature areas, not internal phase numbers. |
| `memory tier`, `T1`-`T8` | **none in active tree** | No action; `.gitignore` line `# Synapse local memory (T6 project tier)` is a comment naming an excluded file, not a live reference. Leave. |
| `design worker` | **none** | No action. |
| `Agent OS` / `AI OS` | **none** | No action. |
| `federation protocol` / `AFP` | **none** | No action. |
| `Ultimate` (rename leftovers) | **none** | No action. |
| `Synapse Protocol v1.0` used as "the A2A protocol" | None after v1.0.1 capability pass — both README and ARCHITECTURE now disambiguate daemon IPC from A2A. | No action. |

## Broken / placeholder links

| Where | What | Action |
|---|---|---|
| `README.md` line 16 | `![Synapse demo](assets/demo.gif)` exists and renders. | Keep, but add named demo GIFs and screenshots in Phase 2. |
| `docs/ARCHITECTURE.md` | All internal links resolve. | Keep. |
| `docs/TRUST_MODEL.md` | Links to `ROADMAP.md` resolve. | Keep. |

## Missing diagrams (Phase 4 will create)

1. `docs/diagrams/architecture.md` — high-level system map
2. `docs/diagrams/identity-flow.md` — issue → sign → verify
3. `docs/diagrams/vault-flow.md` — store → proxy → resolve
4. `docs/diagrams/a2a-task-flow.md` — send → outbox → receive → review → accept → result
5. `docs/diagrams/capability-flow.md` — token issuance → method check → reject/allow
6. `docs/diagrams/trust-flow.md` — outcomes → reputation → gate

## Terminology consistency check

| Term | Standard | Bad variants found | Fix |
|---|---|---|---|
| **A2A** | "the standard A2A protocol (a2aproject.org)" | None remaining | — |
| **Daemon IPC** | "the daemon's internal IPC protocol" | None remaining | — |
| **Capability** | "namespaced `domain.action` string" | Consistent | — |
| **Outbox** | "durable send queue" | Consistent | — |
| **Blob** | "content-addressed file" | Consistent | — |
| **Presence** | "online / busy / offline" (3 states) | Consistent | — |

## Audit summary

- 4 files need REWRITE: `README.md`, `docs/PROTOCOL.md`, `docs/ROADMAP.md`, `SECURITY_REVIEW.md` (root).
- 1 file needs minor edits: `docs/ARCHITECTURE.md` (add v1.0 modules to inventory).
- 3 files need CREATION: `SECURITY.md`, `KNOWN_LIMITATIONS.md`, `docs/diagrams/*.md` (6 diagrams).
- 1 final report: `FINAL_LAUNCH_REPORT.md`.
- 2 example READMEs need REWRITE: `vps-handoff-no-raw-keys`, `malicious-sender-rejection`.
- All other docs: KEEP as-is.

**Zero forbidden architecture references found anywhere in the active tree.**
