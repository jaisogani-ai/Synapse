<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# @synapse/backend-architect-mcp

**MCP #5 (spinout / deprecated)** — backend scaffold helpers (schemas, auth,
queues, microservice splits) generated as **real, runnable code** (not
pseudocode). Not part of Synapse v0.1.0-alpha — see
[`spinout/README.md`](../README.md) for the spinout policy.

## Tools

| Tool | What it generates |
|------|-------------------|
| `backend.scaffold_api` | Full project for **FastAPI · NestJS · Express · Django · Go-Gin · Go-Fiber** with optional `auth`, `rate_limit`, `websockets`, `queues`, and Docker/k8s |
| `backend.design_schema` | Schema as **SQL** (Postgres), **Prisma**, **Django ORM**, or **SQLAlchemy** |
| `backend.design_auth` | **JWT · OAuth · magic-link · SSO** with optional multi-tenancy; `auth0/clerk/supabase/custom` |
| `backend.design_queue` | **Redis (RQ) · RabbitMQ · SQS · Kafka** with retries + DLQ |
| `backend.design_microservices` | Splits a monolith requirement into service boundaries (always emits `api-gateway`) |

Every generator is a pure TypeScript function. The output of `scaffold_api`,
pasted into a fresh project, boots without modification.

```bash
npm install
npm test         # node --test (no build needed)
npm run build    # tsc -> dist/ (publish-ready)
```

License: Apache 2.0.
