<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Architecture Diagrams

Mermaid diagrams describing the actual v1.0 code surface. Render on GitHub natively or with any Mermaid renderer.

| # | Diagram | What it shows |
|---|---|---|
| 1 | [`architecture.md`](architecture.md) | Top-level system map — daemon, SDK, vault MCP, CLI, adapters |
| 2 | [`identity-flow.md`](identity-flow.md) | Issue identity → issue token → sign request → verify |
| 3 | [`vault-flow.md`](vault-flow.md) | Store secret → issue proxy → resolve at daemon → never raw |
| 4 | [`a2a-task-flow.md`](a2a-task-flow.md) | send-task → outbox/online → receive → review → accept → result |
| 5 | [`capability-flow.md`](capability-flow.md) | Token caps → method requirement → grant/deny + audit |
| 6 | [`trust-flow.md`](trust-flow.md) | Record outcome → reputation update → score-based gate |

No diagram in this directory describes a system that does not exist in the v1.0 code. If something is on the diagrams but not in the code, that's a bug.
