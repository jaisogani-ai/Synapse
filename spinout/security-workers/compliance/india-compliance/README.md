<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# India Compliance Workers

> One regulation pack among many — the compliance fleet is pluggable. Synapse
> ships an India pack so teams building in India have something working out of
> the box; add EU/US/APAC packs the same way. **Not** a headline product
> feature.

Five compliance workers for Indian fintech / data products:

| Worker id | Regulation | Model |
|-----------|------------|-------|
| `dpdp_act_2023` | Digital Personal Data Protection Act, 2023 | `claude-haiku-4-5-20251001` |
| `rbi_ai_guidelines` | RBI directions on AI in finance | `claude-opus-4-8` |
| `cert_in_reporting` | CERT-In incident reporting | `claude-haiku-4-5-20251001` |
| `upi_security` | NPCI / UPI security | `claude-haiku-4-5-20251001` |
| `it_act_43a` | IT Act §43A | `claude-sonnet-4-6` |

```python
import india_compliance as ic

ic.all_worker_ids()            # ['dpdp_act_2023', 'rbi_ai_guidelines', ...]
report = ic.run_audit("upi_security")
report.total_checks            # 4
```

> Phase 1 ships the worker definitions and a checklist-producing audit stub.
> Live analysis is wired to the Security Agent fleet in a later phase.

License: Apache 2.0.
