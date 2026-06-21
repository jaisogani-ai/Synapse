<!-- SPDX-License-Identifier: Apache-2.0 -->

# Capability enforcement flow

> Source: `packages/synapse-core/synapse/security/capabilities.py`, `packages/synapse-cli/synapse_cli/receiver.py` (`METHOD_REQUIRED_CAPABILITY`, `_check_capability`), `daemon/src/ipc/mod.rs` (`required_capability_for`).

## A2A receiver — per RPC method

```mermaid
flowchart LR
    REQ[/"inbound POST /a2a<br/>X-A2A-Token = JWT"/]
    PARSE["receiver.handle_request<br/>parse JSON-RPC<br/>extract method"]
    MAP["METHOD_REQUIRED_CAPABILITY<br/><br/>message/send → a2a.send_task<br/>tasks/result → a2a.send_result<br/>tasks/get → a2a.read_status"]
    TOKEN{"token present?"}
    VERIFY["ZeroTrustNetwork.verify_request(<br/>  token,<br/>  required_cap,<br/>  payload, sig)"]
    SUBJECT{"claims.sub == sender_id?"}
    ALLOW[/"dispatch to method handler"/]
    DENY["audit: reject_capability<br/>HTTP 200 + JSON-RPC error<br/>'capability denied: ...'"]

    REQ --> PARSE --> MAP --> TOKEN
    TOKEN -- no --> DENY
    TOKEN -- yes --> VERIFY
    VERIFY -- token bad or<br/>cap not granted --> DENY
    VERIFY -- ok --> SUBJECT
    SUBJECT -- no --> DENY
    SUBJECT -- yes --> ALLOW

    style ALLOW fill:#e8ffe8
    style DENY fill:#ffe8e8
```

## Rust daemon IPC — per TrustOp

```mermaid
flowchart LR
    IPC[/"connection on Unix socket<br/>SynapseMessage with caps: Vec<String>"/]
    DISPATCH["ipc::dispatch<br/>parse message"]
    OP["TrustOp variant<br/><br/>RecordOutcome → trust.write<br/>GetScore → trust.read<br/>ShouldTrust → trust.read<br/>RankAgents → trust.read"]
    CHECK{"is_granted(caps, required)?<br/>(handles wildcards: ns.* and *)"}
    EXEC[/"execute against TrustStore"/]
    REJECT["error_code::CAPABILITY_DENIED<br/>{ code, message: 'capability X not granted' }"]

    IPC --> DISPATCH --> OP --> CHECK
    CHECK -- yes --> EXEC
    CHECK -- no --> REJECT

    style EXEC fill:#e8ffe8
    style REJECT fill:#ffe8e8
```

## Capability vocabulary (subset)

| Capability | Granted by default? | Used by |
|---|---|---|
| `a2a.send_task` | Yes (default A2A grant) | Sender — A2A `message/send` |
| `a2a.send_result` | Yes (default A2A grant) | Receiver-acting-as-sender — A2A `tasks/result` |
| `a2a.read_status` | Yes (default A2A grant) | Either side — A2A `tasks/get` |
| `trust.read` | No | Rust IPC clients reading reputation |
| `trust.write` | No | Rust IPC clients recording outcomes |
| `vault.request_credential` | No | Adapters requesting a proxy |
| `vault.store_secret` | No | Operator-only on the laptop |
| `*` | Reserved for the daemon's self-signed requests | Never grant to a remote agent |
