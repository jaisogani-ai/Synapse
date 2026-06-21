<!-- SPDX-License-Identifier: Apache-2.0 -->

# High-level architecture

> Source of truth: `daemon/src/`, `packages/synapse-core/`, `packages/synapse-vault-mcp/`, `packages/synapse-cli/`, `packages/adapters/`.

```mermaid
graph TB
    subgraph LOCAL_HOST["Local host (one per device)"]
        DAEMON["synapsed<br/>(Rust daemon)<br/><br/>• trust store<br/>• internal IPC<br/>• capability enforcement"]
        CLI["synapse CLI<br/>(Python)<br/><br/>• send-task / inbox / outbox<br/>• presence / review<br/>• vault_client"]
        VAULT["synapse-vault-mcp<br/>(Node)<br/><br/>• AES-256-GCM<br/>• scoped proxies<br/>• audit log"]
        ADAPTER["adapters<br/>(Claude Code, Cursor,<br/>Codex, VS Code,<br/>Antigravity)"]
        STATE[("~/.synapse/<br/>identity.json<br/>trust.json<br/>inbox.db<br/>outbox.db<br/>audit.jsonl<br/>blobs/")]
    end

    REMOTE["Other agent<br/>(another host / account)"]

    ADAPTER -- "register / sign /<br/>request vault" --> CLI
    CLI -- "internal IPC<br/>(Unix socket)" --> DAEMON
    CLI -- "Node bridge<br/>(stdin/stdout JSON)" --> VAULT
    CLI -- "read/write" --> STATE

    CLI -- "standard A2A<br/>JSON-RPC over HTTP<br/>+ HMAC + JWT" --> REMOTE
    REMOTE -- "tasks/result" --> CLI

    style DAEMON fill:#e8f4ff
    style VAULT fill:#fff5e6
    style CLI fill:#f0ffe6
    style ADAPTER fill:#f9e8ff
    style STATE fill:#f8f8f8
```

## What each box owns

| Component | Owns |
|---|---|
| **synapsed** (Rust daemon) | Trust store, internal IPC protocol, capability enforcement on each TrustOp. Not on the A2A path. |
| **synapse CLI** (Python) | The actual A2A endpoints. send-task, inbox, outbox, presence, review. Issues tokens. Verifies signatures. Enforces capability on inbound A2A. |
| **synapse-vault-mcp** (Node) | The only place a raw secret exists at rest. Issues proxy tokens. Resolves proxies. |
| **adapters** (Python) | Thin wrappers that give Claude Code / Cursor / etc. a uniform `register` + `sign_message` + `request_vault_credential` API. |
| **~/.synapse/** | All persistent state. Backup-friendly, inspect-friendly. |
