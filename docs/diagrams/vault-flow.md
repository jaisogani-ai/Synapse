<!-- SPDX-License-Identifier: Apache-2.0 -->

# Vault flow

> Source: `packages/synapse-vault-mcp/src/vault.ts`, `packages/synapse-cli/synapse_cli/vault_client.py`.

```mermaid
sequenceDiagram
    autonumber
    participant Operator as Operator<br/>(laptop)
    participant Vault as SecretVault<br/>(AES-256-GCM)
    participant Agent as Agent<br/>(Codex on VPS)
    participant Daemon as Synapse daemon<br/>(resolves proxy)
    participant API as Remote API<br/>(e.g. api.anthropic.com)

    Note over Operator,Vault: 1 — store (one-time, on the operator's laptop)
    Operator->>Vault: storeSecret("anthropic-api", "sk-ant-real-key")
    Vault->>Vault: encrypt with AES-256-GCM<br/>+ random IV per write
    Vault-->>Operator: ok (raw value never returned)

    Note over Agent,Vault: 2 — request a scoped proxy (per task)
    Agent->>Vault: requestCredential(service, purpose, ttl=300s)
    Vault->>Vault: generate token = random 24 bytes hex<br/>store (token → service, expiresAt)
    Vault-->>Agent: { proxyUrl: synapse+vault://proxy/<token>,<br/>proxyToken, service, expiresAt }

    Note over Agent,API: 3 — agent uses the proxy URL, never the raw key
    Agent->>Daemon: outbound API call routed through proxy
    Daemon->>Vault: resolveProxy(token)
    Vault->>Vault: check expiry, look up service<br/>decrypt ciphertext (AES-256-GCM)
    Vault-->>Daemon: raw secret (daemon-side only)
    Daemon->>API: Authorization: Bearer <raw>
    API-->>Daemon: response
    Daemon-->>Agent: response (raw secret stripped)

    Note over Vault: 4 — audit
    Vault->>Vault: append entries:<br/>store / issue_proxy / resolve_proxy<br/>(never the raw value)
```

## Invariants

- **Raw secret never returns through `requestCredential`.** Agents always get a proxy.
- **Raw secret never crosses the A2A wire.** The vault MCP runs locally on the operator's laptop; only the daemon resolves the proxy at the network egress point.
- **Every action audited.** `audit_log()` returns `{ action, name, at, purpose }`. The value never appears.
- **Tampered ciphertext fails GCM auth tag check on decrypt.** Test: `tampered ciphertext is rejected on decrypt`.
