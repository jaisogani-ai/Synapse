<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# synapse-core

The Python SDK for Synapse — identity, trust, and security primitives for AI agents.

- **`synapse.security.zero_trust`** — JWT (HS256) identity issuance + HMAC request signing.
- **`synapse.security.capabilities`** — capability-based authorization model.
- **`synapse.security.secret_detector`** — 140+ secret-type detector with entropy fallback.
- **`synapse.security.supply_chain`** — OSV.dev CVE lookup + entropy-based supply-chain scanning.

```python
from synapse.security import ZeroTrustNetwork, CapabilitySet

network = ZeroTrustNetwork()
identity = network.issue_identity("agent-1", capabilities=CapabilitySet.from_strings(["trust.read"]))
```

License: Apache 2.0.
