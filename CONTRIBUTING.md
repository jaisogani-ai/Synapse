<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Contributing to Synapse

Thanks for thinking about contributing. Synapse is small on purpose; the contribution flow is correspondingly simple. Please read this whole file before opening your first PR.

## Project scope (read first)

Synapse is a trust layer for A2A. It is **not** any of these — proposals for any of them will be politely declined:

- A federation protocol
- A memory layer
- An agent runtime / orchestration framework
- A multi-tenant SaaS
- An "agent OS" / "AI OS"
- An agent or skill marketplace
- A new wire protocol (we sign and verify A2A, we do not fork it)

If your idea is one of those, it might be a great project — just not this one.

Things we welcome:

- Bug reports and small focused fixes
- Tests that close coverage gaps
- Documentation improvements (especially examples)
- Adapter contributions for AI tools beyond the existing 5
- Security findings (see `SECURITY.md` — please don't open public issues for vulnerabilities)
- Performance improvements with measurements
- A platform port (Linux is supported, Windows is untested — PRs welcome)

## Getting set up

```bash
git clone https://github.com/jaisogani-ai/synapse.git synapse
cd synapse
npm install
npm --workspace @synapse/secret-vault-mcp run build
pip install -e ".[dev]"
cargo build --release

# all three test suites must pass before you push
cargo test
pytest -q
npm test
```

## Branch + commit conventions

- Branch off `main`. Feature branches: `feature/<short-name>`. Fixes: `fix/<short-name>`. Docs: `docs/<short-name>`.
- Commit messages start with one of: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `perf:`. Imperative mood (`fix: handle empty token`, not `fixed empty token`).
- Keep commits small and self-contained. A PR with 1 logical change is easier to merge than one with 4.

## Code style

- **Python** — PEP 8, type hints on public function signatures, immutable dataclasses (`frozen=True`) for data carriers. We run `ruff` (`F401`/`F841` clean is enforced; `pyproject.toml` defines the config).
- **Rust** — `cargo fmt` clean. `cargo clippy` warnings are not yet a hard gate but the trend is toward zero. Idiomatic ownership, `?` for errors, structured errors via `thiserror`.
- **TypeScript** — strict mode, no `any` in new code, dependency-free where possible (the vault MCP intentionally uses only `node:crypto`).
- **No comments restating the code.** Comments should explain *why*, not *what*.
- **No TODOs in main.** Either open an issue or leave it in your branch.

## Tests

Every behavior change ships with a test. We're not picky about the style; we are picky about the test actually exercising the behavior change.

- Unit tests: alongside their module under `tests/` or `tests_*`.
- Integration tests: `daemon/tests/` for Rust, `packages/*/tests/` for Python.
- E2E demo scripts live under `examples/`.

Coverage target: don't lower it. The current suites pass 128 / 128 — your PR should keep that number monotonically non-decreasing.

## Documentation

- Update `README.md` if the user-visible surface changes.
- Update `docs/ARCHITECTURE.md` if you add or rename a module.
- Update `docs/ROADMAP.md` if you close a planned item.
- Update `CHANGELOG.md` (the `Unreleased` section) for every PR.
- Update `KNOWN_LIMITATIONS.md` if you discover a new gap.
- For security-relevant changes, also update `SECURITY_REVIEW.md`.

## Security

Vulnerability reports go via `SECURITY.md`. Do **not** open a public issue for a security vulnerability.

Non-security bugs: open an issue first if the fix isn't obvious. Quick fixes can go straight to a PR.

## PR checklist

Before requesting review:

- [ ] All three test suites pass locally (`cargo test`, `pytest`, `npm test`)
- [ ] `ruff check --select=F401,F841 packages` is clean
- [ ] Docs updated (README + ARCHITECTURE + CHANGELOG at minimum)
- [ ] No new TODOs / FIXMEs added
- [ ] Commit message follows the convention above
- [ ] No secrets in commits — `secret_detector.py` finds none on your changed files

## Code of conduct

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Be respectful, be specific, give context. Code review is about the code, not the person.

## Licensing

By contributing, you agree your contribution will be licensed under [Apache 2.0](LICENSE), matching the rest of the project. The repo includes a `NOTICE` file; please add yourself if your contribution is significant.

## Questions

Open a GitHub Discussion if it's a question about direction or design. Open an Issue if it's a bug or a feature proposal. Open a PR if it's a fix.
