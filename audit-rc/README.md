# Synapse v1 RC Audit

**Date:** 2026-06-21
**Scope:** Public-launch readiness for `Synapse` under Apache 2.0.

This directory contains 8 independent audit reports plus a drop-in
replacement README and architecture document. No code was modified.

## Reports

| # | File | What it answers |
|---|------|-----------------|
| 0 | [`REPOSITORY_INVENTORY.md`](REPOSITORY_INVENTORY.md) | What is actually in this repo? Per-subsystem reality. |
| 1 | [`LEGAL_AUDIT.md`](LEGAL_AUDIT.md) | Is the licence / NOTICE / per-file SPDX work clean? |
| 2 | [`DOC_AUDIT.md`](DOC_AUDIT.md) | Where does documentation lie about the code? |
| 3 | [`README_REWRITE.md`](README_REWRITE.md) | Drop-in replacement for the root `README.md`. |
| 4 | [`ARCHITECTURE_REALITY.md`](ARCHITECTURE_REALITY.md) | Drop-in replacement for `docs/ARCHITECTURE.md`. |
| 5 | [`SECURITY_REVIEW.md`](SECURITY_REVIEW.md) | What did Phase 4 close? What is still open? |
| 6 | [`GITHUB_REVIEW.md`](GITHUB_REVIEW.md) | What will Hacker News / r/rust / r/netsec do with this? |
| 7 | [`RELEASE_SCORE.md`](RELEASE_SCORE.md) | 0–10 scores per dimension + the ordered launch checklist. |

## Headline finding

> **Not ready today. Ready in 75 minutes.**

Three small fixes — wire `__main__.py`, fix `package.json` workspaces, label
the vps-handoff demo honestly — close 80% of the gap. After those, swap in
the rewritten `README.md` and `ARCHITECTURE.md` from this directory, and
Synapse is launch-worthy.

See [`RELEASE_SCORE.md`](RELEASE_SCORE.md) for the ordered checklist.
