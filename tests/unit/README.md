<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# tests/unit

Cross-language unit tests for Synapse.

## Python (this directory)

Run from the repo root with the dev extras installed:

```bash
pip install -e ".[dev]"
pytest
```

| File | Covers |
|------|--------|
| `test_zero_trust.py` | JWT identity issuance + HMAC request signing |
| `test_capabilities.py` | Capability-based authorization system |
| `test_secret_detector.py` | 140+ secret pattern detector |
| `test_supply_chain.py` | OSV.dev + entropy supply-chain scanner |

## Rust (trust store, protocol, IPC)

The Rust unit + integration tests live with the daemon crate (idiomatic Rust):

- **Inline unit tests** — `#[cfg(test)]` modules inside
  `daemon/src/trust/reputation.rs`, `protocol/mod.rs`, `ipc/mod.rs`,
  and `security/capability.rs`.
- **Integration tests** — `daemon/tests/trust_reputation.rs`,
  `protocol.rs`, `engine.rs`, and `ipc_socket.rs`.

Run them with:

```bash
~/.cargo/bin/cargo test
```
