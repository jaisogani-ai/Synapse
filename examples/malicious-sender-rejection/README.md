<!-- SPDX-License-Identifier: Apache-2.0 -->

# Demo 3 — Malicious sender rejection

> **What it shows.** Three attack vectors hit the receiver. All three are rejected, audited, and the receiver survives to process a legitimate task right after.

## Attack vectors covered

1. **Unsigned message.** Empty `X-A2A-Sender` and `X-A2A-Signature` headers. Receiver rejects at Gate 1 with audit `reject_unsigned` / detail `missing_sender_or_signature`.
2. **Forged signature.** A valid sender id, a wrong HMAC payload signature, and a missing or stale timestamp. Receiver rejects at Gate 1 with audit `reject_unsigned` / detail `missing_timestamp` or `bad_signature_or_stale`.
3. **Low-reputation sender** with a valid signature **and** a valid capability token. The message lands in the inbox but `synapse inbox list` redacts the content with `<redacted: low-reputation sender, run synapse inbox accept to view>`. Gate 2 in action.

After the three attacks the demo sends a legitimate task to prove the receiver is alive and that the gates didn't cause a side-effect that broke it.

> **Capability enforcement is also live in this demo** (Gate 3, v1.0.1). If a sender ships a request without a capability token — or with a token whose `caps` don't include `a2a.send_task` — the receiver rejects with audit `reject_capability`. This is exercised separately in `packages/synapse-cli/tests/test_capability_enforcement.py` (7 tests covering deny-by-default, insufficient cap, subject mismatch, happy path, wildcard, escape hatch).

## What you'll see

```
══════════════════════════════════════════════════════════════════
  SYNAPSE V1 — MALICIOUS SENDER REJECTION DEMO
══════════════════════════════════════════════════════════════════

ATTACK 1 — Unsigned message
  ✗ rejected
  audit: reject_unsigned  from=evil-agent  missing_sender_or_signature

ATTACK 2 — Forged signature
  ✗ rejected
  audit: reject_unsigned  from=trusted-alice  missing_timestamp

ATTACK 3 — Low-reputation sender (score 0.1)
  ✓ queued
  inbox list preview: <redacted: low-reputation sender, run synapse inbox accept to view>

──────────────────────────────────────────────────────────────────
LEGITIMATE — trusted sender (score 0.9)
  ✓ accepted, content visible

══════════════════════════════════════════════════════════════════
  RESULT: PASS
══════════════════════════════════════════════════════════════════
  ✓ Unsigned message rejected + audit logged
  ✓ Forged signature rejected + audit logged
  ✓ Low-rep sender content redacted
  ✓ Receiver survived — legitimate task accepted
```

## Architecture sketch

```
   evil-agent  ─────►  ┌──────────────────────────┐
   (no headers)        │       RECEIVER           │      audit
                       │                          │
   trusted-alice ─────►│  Gate 1: HMAC + ts       │ ───► reject_unsigned
   (bad sig)           │   ✗ fail                 │
                       │                          │
                       │  Gate 2: reputation      │
   low-rep-dave  ─────►│   pass (queued, but      │ ───► receive_task
   (rep 0.1)           │   list shows redacted)   │      (preview redacted)
                       │                          │
                       │  Gate 3: capability      │ ───► reject_capability
   no-token-eve  ─────►│   ✗ token missing        │      (covered in unit tests)
                       │                          │
   trusted-alice ─────►│  all gates pass          │ ───► receive_task
   (rep 0.9)           │   ✓ delivered            │      preview visible
                       └──────────────────────────┘
```

## Run

```bash
# from repo root
python3.11 examples/malicious-sender-rejection/demo.py
```

Exit code 0 on PASS.

## Recording instructions

```bash
asciinema rec --command "python3.11 examples/malicious-sender-rejection/demo.py" /tmp/demo.cast
agg /tmp/demo.cast assets/demo-block.gif
```

Place the recording at `assets/demo-block.gif`. The root README references it.

## Why this proves what it proves

- The receiver in the demo is the same `ReceivingDaemon` class the CLI uses. **No alternative implementation, no permissive test mode.**
- The three Gate failures produce real `audit.jsonl` entries via the real `AuditLog`. After the run you can `cat` the file and see them.
- The legitimate-sender step at the end isn't decoration — it proves the gates' rejections did not corrupt the receiver's state.
- Capability enforcement is verified by `packages/synapse-cli/tests/test_capability_enforcement.py`; the demo doesn't repeat those scenarios but the receiver enforces them on every hit it processes here.
