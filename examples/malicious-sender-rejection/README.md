<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Demo: Malicious Sender Rejection

Three attack vectors against a Synapse-protected A2A receiver. All stopped.

## What it proves

| Attack | Expected result |
|--------|----------------|
| Unsigned message (empty signature) | Rejected immediately, audit logged |
| Forged signature (wrong HMAC key) | Rejected immediately, audit logged |
| Low-reputation sender (valid sig, score=0.1) | Queued but content **redacted** until explicit accept |
| Legitimate sender after attacks | Accepted normally — receiver never crashed |

## Run

```bash
cd synapse/
python3 examples/malicious-sender-rejection/demo.py
```

## Architecture

The demo spins up a single `ReceivingDaemon` on a random local port, then
fires four requests in sequence. No Docker, no external services.

The rejection logic lives in `synapse_cli/receiver.py` — the same code that
runs in the cross-device task delegation demo and the production CLI.
