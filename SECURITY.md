<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Security Policy

> Synapse is a security tool. Vulnerability reports are taken seriously and answered fast.

## Supported versions

| Version | Supported | Notes |
|---|---|---|
| **1.0.x** | ✅ Yes | Current release line. All security fixes land here. |
| < 1.0 (pre-release tags) | ❌ No | Replace with 1.0.x. |

We do not back-port security fixes to pre-1.0 tags. If you are on a pre-release commit, upgrade to the latest 1.0.x tag.

## Reporting a vulnerability

**Do not open a public issue for a security vulnerability.**

Report via one of:

1. **GitHub Security Advisory** — preferred. Use the "Report a vulnerability" button on the repo's Security tab.
2. **Email** — `jaisogani183@gmail.com` with subject prefix `[synapse-security]`. PGP available on request.

Please include:

- A description of the issue and its impact.
- Steps to reproduce (a minimal proof-of-concept is ideal).
- Affected version / commit SHA.
- Any suggested mitigation you have in mind.
- Whether you'd like public credit when the advisory is published.

### What counts as a vulnerability

- Anything that breaks one of the three Trust Model gates (signature, reputation, capability).
- Anything that exposes a raw secret outside the vault.
- Anything that lets a forged or replayed message land in an inbox or audit log.
- Anything that lets one agent's token authorize another agent's action (subject mismatch, token confusion).
- Any cryptographic weakness in the HMAC, JWT, or AES-256-GCM use.
- Any path that lets a sender bypass the capability check on a method.
- Any way to truncate, rewrite, or backdate the audit log such that a real event disappears.
- A directory traversal, SSRF, or unbounded-resource path in the receiver or blob server.

### What does not count

- Theoretical attacks that require the operator to grant `*` to an untrusted agent. The `*` wildcard is reserved for the daemon's own self-signed requests; documented as such.
- A receiver crashing on a malformed input where no exfiltration or escalation is possible — file an ordinary bug instead, we'll still fix it.
- Findings in `spinout/` — those modules are not part of v1.0 and are excluded from the security boundary. They are marked deprecated.

## Response timelines

Synapse is currently maintained by one person. Commitments below are best-effort; we will always respond, but the SLA reflects single-maintainer reality.

| Stage | Target | Maximum |
|---|---|---|
| Acknowledge report | within **48 hours** | 7 days |
| Initial triage (severity + scope) | within **5 business days** | 14 days |
| Fix landed on `main` | within **30 days** of triage, severity-weighted (CRITICAL: 7 days; HIGH: 21 days; MEDIUM: 60 days; LOW: next release) | 90 days |
| Public advisory + release | within **7 days of fix** for CRITICAL/HIGH; with next release for MEDIUM/LOW | — |

## Disclosure policy

We follow **coordinated disclosure**:

1. You report privately. We confirm receipt.
2. We work with you on a fix and a public advisory.
3. We do not publish details until the fix is released **and** at least 7 days have passed (or 30 days if the maintainer needs more time for any reason — communicated to you in advance).
4. We credit you in the advisory unless you ask us not to.
5. If a vulnerability is being actively exploited in the wild, we accept faster disclosure timelines coordinated case-by-case.

If you don't hear back within 7 days, please ping again — email rules can be unkind.

## Security advisories

Published advisories live at the repo's Security tab and in `audit-rc/` for historical context. A CHANGELOG entry references each CVE / GHSA id.

## Out of scope

- Issues only reproducible with `pip install`-ed older versions where the fix already shipped.
- Operator misconfiguration (e.g. setting trust score to 0.99 for an unknown sender, granting `*` to a remote agent).
- Issues in third-party dependencies — please report those upstream. We will track the advisory and bump versions, but the original disclosure should go to the vendor.

## Bug bounty

Synapse does not currently run a paid bounty program. We will publicly credit good reports and link to your homepage / Twitter / Mastodon / blog post in the advisory if you'd like.
