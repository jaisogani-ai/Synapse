<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# synapse-router

> **Spinout / deprecated.** Not part of Synapse v0.1.0-alpha — see [`spinout/README.md`](../README.md) for the spinout policy.

The Synapse **Intelligent Router** — routes each task to the cheapest model
that does it well, and proves the savings in real dollars.

```python
from synapse.router import route, headline_example

route("architecture_decision")  # 'claude-opus-4-8'
route("documentation")          # 'claude-sonnet-4-6'
route("json_formatting")        # 'claude-haiku-4-5-20251001'
route("anything", offline_mode=True)  # 'ollama:llama-3.3-70b'

report = headline_example()
print(report.baseline_opus_usd, "->", report.routed_usd)
print(f"{report.savings_pct}% saved")   # ~85% saved
```

| Tier | Model | Example tasks |
|------|-------|---------------|
| Deep reasoning | `claude-opus-4-8` | architecture, security audit, complex codegen |
| Medium | `claude-sonnet-4-6` | feature specs, docs, code review |
| Fast/cheap | `claude-haiku-4-5-20251001` | json formatting, classification, secret scan |
| Local fallback | `ollama:llama-3.3-70b` | offline / cost-capped |

License: Apache 2.0.
