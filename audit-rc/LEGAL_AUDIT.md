# LEGAL_AUDIT

**Date:** 2026-06-21
**Scope:** `LICENSE`, `NOTICE`, every Cargo.toml / pyproject.toml / package.json, every source-file header.

---

## Top-level legal artifacts

| Artifact | Result | Detail |
|----------|--------|--------|
| `LICENSE` | **PASS** | 202 lines, fetched from `apache.org/licenses/LICENSE-2.0.txt`, unmodified. SHA-comparable to upstream. |
| `NOTICE` | **PASS** | Exact 5-line content specified in the licence task: copyright 2026 Jai Sogani, GitHub handle, attribution. |
| Apache 2.0 standard text unmodified | **PASS** | No Commons Clause, no field-of-use restriction, no "non-commercial only" rider. |
| Copyright year/owner | **PASS** | All 12 manifests and all 80+ source headers say "Copyright (c) 2026 Jai Sogani". No `<YOUR NAME HERE>`-style placeholders. |
| Conflicting licenses | **PASS** | Single licence (`Apache-2.0`) declared in every manifest. No mixed-licence content found in the source tree. |
| Stale branding | **PASS** | All headers / docs use "Synapse" + "Jai Sogani". No "Anthropic", "Claude", "OpenAI", "OpenClaw", "Plankton", or other foreign brands found in source. |

---

## Per-package result

### Rust workspace

| Path | License field | SPDX header in TOML? | Result |
|------|---------------|---------------------|--------|
| `Cargo.toml` (workspace root) | `license = "Apache-2.0"` (workspace.package) | yes (line 1) | **PASS** |
| `daemon/Cargo.toml` | `license.workspace = true` (inherits) | yes (line 1) | **PASS** |

### Python packages

| Path | License field | Result |
|------|--------------|--------|
| `pyproject.toml` (root) | `license = { text = "Apache-2.0" }` | **PASS** |
| `packages/synapse-core/pyproject.toml` | `license = { text = "Apache-2.0" }` | **PASS** |
| `packages/synapse-cli/pyproject.toml` | `license = { text = "Apache-2.0" }` | **PASS** |
| `spinout/synapse-router/pyproject.toml` | `license = { text = "Apache-2.0" }` | **PASS** |

### TypeScript packages

| Path | License field | Result |
|------|--------------|--------|
| `package.json` (root) | `"license": "Apache-2.0"` | **WARNING** — license is fine, but the `"workspaces"` array points to `packages/synapse-trust-mcp` (empty dir) and `packages/synapse-cli` (Python). `npm install` will fail; this is a launch blocker tracked in `GITHUB_REVIEW.md` (not legal). |
| `packages/synapse-vault-mcp/package.json` | `"license": "Apache-2.0"` | **PASS** |
| `spinout/synapse-memory-mcp/package.json` | `"license": "Apache-2.0"` | **PASS** |
| `spinout/synapse-context-mcp/package.json` | `"license": "Apache-2.0"` | **PASS** |
| `spinout/synapse-skills-mcp/package.json` | `"license": "Apache-2.0"` | **PASS** |
| `spinout/synapse-backend-architect-mcp/package.json` | `"license": "Apache-2.0"` | **PASS** |

---

## Source-file headers

| Language | Files (excluding build artifacts) | With SPDX + copyright header | Result |
|----------|-----------------------------------|-----------------------------|--------|
| Rust (`*.rs`) | 12 | 12 | **PASS** |
| Python (`*.py`, excluding `__pycache__`) | 47 | 47 | **PASS** |
| TypeScript (`*.ts`) | 29 | 29 | **PASS** |
| Markdown (top-level docs) | 6 | 6 (all carry SPDX HTML comment) | **PASS** |

Headers verified via `head -3` over every source file. The single previously-missing file (`packages/synapse-cli/tests/__init__.py`) was filled during the licence-enhancement task in the previous turn.

---

## Third-party content audit

| Item | Reality | Result |
|------|---------|--------|
| Bundled third-party source | None found in `daemon/`, `packages/`, `spinout/` (excluding `target/` build artifacts) | **PASS** |
| Vendored binaries | None | **PASS** |
| Embedded test fixtures with their own licence | None | **PASS** |
| README badges / linked logos | Two `img.shields.io` SVG badges in `README.md`, both render at request-time and are not bundled — no embedded copyrighted assets | **PASS** |
| Apache APPENDIX boilerplate | Present in `LICENSE` (lines 187–202) — the template, not a per-file copy | **PASS** |

---

## NOTICE accuracy

The Apache 2.0 requires that `NOTICE` content be reproduced by anyone redistributing the work. Current `NOTICE`:

```
Synapse — Identity, Trust, and Secret Handoff for AI Agents
Copyright 2026 Jai Sogani (github.com/jaisogani-ai)
Built in Jaipur, India.

This product includes software developed by Jai Sogani.
```

| Check | Result |
|-------|--------|
| One short attribution paragraph | **PASS** |
| Does not modify licence terms | **PASS** |
| No placeholder text | **PASS** |
| Tagline matches `README.md` | **PASS** |

---

## Overall verdict

**ALL PASS** for legal/licensing.

The single yellow flag (`package.json` workspaces pointing to empty directories) is a build issue, not a legal one — Apache-2.0 declaration is unaffected. Tracked under `GITHUB_REVIEW.md` § "What will they attack" and `RELEASE_SCORE.md` § "Launch Readiness".

The repository is **legally ready** for public Apache 2.0 release under the name **Synapse**, copyright 2026 Jai Sogani.
