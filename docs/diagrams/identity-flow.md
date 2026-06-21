<!-- SPDX-License-Identifier: Apache-2.0 -->

# Identity flow

> Source: `packages/synapse-core/synapse/security/zero_trust.py`, `packages/synapse-cli/synapse_cli/a2a_signer.py`.

```mermaid
sequenceDiagram
    autonumber
    participant Adapter as Adapter<br/>(claude-code / cursor / ...)
    participant Network as ZeroTrustNetwork<br/>(in-process)
    participant Signer as A2ASigner
    participant Receiver

    Note over Adapter,Network: 1 — issue identity (once per agent)
    Adapter->>Network: issue_identity("alice")
    Network-->>Adapter: AgentIdentity(secret=256-bit random)

    Note over Adapter,Network: 2 — issue token (per send, 15-min TTL)
    Adapter->>Network: issue_token("alice", caps=["a2a.send_task", ...])
    Network-->>Adapter: JWT(sub=alice, iat, exp, caps, signature=HS256)

    Note over Adapter,Signer: 3 — sign request body (per send)
    Adapter->>Signer: sign("alice", payload_bytes)
    Signer->>Network: sign_payload("alice", payload + "|" + ts)
    Network-->>Signer: hmac_sha256_hex
    Signer-->>Adapter: SignedA2APayload(payload, sig, ts)

    Note over Adapter,Receiver: 4 — POST with all of the above on the wire
    Adapter->>Receiver: POST /a2a<br/>X-A2A-Sender, X-A2A-Signature,<br/>X-A2A-Timestamp, X-A2A-Token

    Note over Receiver: 5 — verify
    Receiver->>Receiver: verify_raw(sender, body, sig, ts)<br/>then verify_request(token, required_cap)
    Receiver-->>Adapter: 200 result | capability_denied | bad_signature
```

## Where each piece is stored

| Material | Lifetime | Stored where |
|---|---|---|
| Agent HMAC secret | persistent per agent | `ZeroTrustNetwork._secrets` (process memory). Persistent agents must re-issue at startup or persist out-of-band. |
| JWT | 15 min | not stored — issued per send |
| HMAC signature | per request | bound into HTTP headers, never persisted on the sender side |
