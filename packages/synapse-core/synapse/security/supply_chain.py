# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Supply Chain Scanner — validate MCP servers, plugins, and packages.

Two complementary signals:

1. **Known vulnerabilities** via the OSV.dev API (https://osv.dev). The HTTP
   call is behind an injectable ``fetcher`` so tests run fully offline.
2. **Obfuscation heuristics** via Shannon entropy — unusually high-entropy
   strings in an install script or manifest are a classic supply-chain smell.

A :class:`ScanReport` ends in a recommendation: ``trust`` / ``review`` /
``reject``. 1,800+ MCP servers were found exposed without auth in 2026; this
scanner is what lets the daemon refuse to trust them blindly.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from typing import Callable

#: OSV.dev batch/single query endpoint.
OSV_QUERY_URL = "https://api.osv.dev/v1/query"

#: Entropy (bits/char) above which a token is treated as suspicious.
SUSPICIOUS_ENTROPY = 4.5

#: A fetcher takes ``(url, json_body)`` and returns the parsed JSON response.
Fetcher = Callable[[str, dict], dict]


def shannon_entropy(text: str) -> float:
    """Return the Shannon entropy of ``text`` in bits per character."""
    if not text:
        return 0.0
    counts = Counter(text)
    length = len(text)
    return -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )


@dataclass(frozen=True)
class Vulnerability:
    """A single known vulnerability from OSV."""

    id: str
    summary: str
    severity: str = "unknown"


@dataclass(frozen=True)
class ScanReport:
    """The result of scanning a package or MCP server."""

    target: str
    requires_auth: bool
    code_signed: bool
    sbom_present: bool
    known_cves: tuple[Vulnerability, ...] = ()
    reputation_score: float = 50.0
    high_entropy_findings: tuple[str, ...] = ()
    recommendation: str = "review"  # trust | review | reject
    notes: tuple[str, ...] = ()


def _default_fetcher(url: str, body: dict) -> dict:
    """POST ``body`` as JSON to ``url`` using the standard library.

    Only used in production; tests inject a fake fetcher.
    """
    import urllib.request  # local import keeps the module import-light

    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


class OsvClient:
    """A tiny OSV.dev client with an injectable transport."""

    def __init__(self, fetcher: Fetcher | None = None) -> None:
        """Create a client. ``fetcher`` defaults to a urllib-based POST."""
        self._fetcher = fetcher or _default_fetcher

    def query_package(
        self, ecosystem: str, name: str, version: str
    ) -> list[Vulnerability]:
        """Return known vulnerabilities for a package version (may be empty)."""
        body = {
            "version": version,
            "package": {"name": name, "ecosystem": ecosystem},
        }
        response = self._fetcher(OSV_QUERY_URL, body)
        return _parse_osv_vulns(response)


def _parse_osv_vulns(response: dict) -> list[Vulnerability]:
    """Map an OSV query response to :class:`Vulnerability` objects."""
    out: list[Vulnerability] = []
    for vuln in response.get("vulns", []) or []:
        severity = "unknown"
        severities = vuln.get("severity") or []
        if severities:
            severity = str(severities[0].get("score", "unknown"))
        out.append(
            Vulnerability(
                id=vuln.get("id", "UNKNOWN"),
                summary=vuln.get("summary", vuln.get("details", ""))[:200],
                severity=severity,
            )
        )
    return out


class SupplyChainScanner:
    """Validate packages and MCP servers before the daemon trusts them."""

    def __init__(self, osv: OsvClient | None = None) -> None:
        """Create a scanner. ``osv`` defaults to a live :class:`OsvClient`."""
        self._osv = osv or OsvClient()

    def scan_package(
        self, ecosystem: str, name: str, version: str
    ) -> ScanReport:
        """Scan a single dependency for known vulnerabilities."""
        vulns = tuple(self._osv.query_package(ecosystem, name, version))
        recommendation = "reject" if vulns else "trust"
        return ScanReport(
            target=f"{ecosystem}:{name}@{version}",
            requires_auth=True,
            code_signed=False,
            sbom_present=False,
            known_cves=vulns,
            recommendation=recommendation,
            notes=(f"{len(vulns)} known vulnerability(ies)",),
        )

    def scan_mcp_server(
        self,
        url: str,
        *,
        requires_auth: bool,
        code_signed: bool = False,
        sbom_present: bool = False,
        reputation_score: float = 50.0,
        manifest: dict | None = None,
    ) -> ScanReport:
        """Scan an MCP server's posture and manifest, returning a recommendation."""
        findings = _scan_manifest_entropy(manifest or {})
        recommendation = _recommend(
            requires_auth=requires_auth,
            code_signed=code_signed,
            reputation_score=reputation_score,
            high_entropy_count=len(findings),
        )
        return ScanReport(
            target=url,
            requires_auth=requires_auth,
            code_signed=code_signed,
            sbom_present=sbom_present,
            reputation_score=reputation_score,
            high_entropy_findings=tuple(findings),
            recommendation=recommendation,
            notes=("no authentication required",) if not requires_auth else (),
        )


def _scan_manifest_entropy(manifest: dict) -> list[str]:
    """Flag suspicious high-entropy string values in a manifest."""
    findings: list[str] = []
    for value in _iter_strings(manifest):
        token = value.strip()
        if len(token) >= 20 and shannon_entropy(token) >= SUSPICIOUS_ENTROPY:
            findings.append(token[:12] + "…")
    return findings


def _iter_strings(obj: object):
    """Yield every string value nested anywhere in ``obj``."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _iter_strings(value)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _iter_strings(item)


def _recommend(
    *,
    requires_auth: bool,
    code_signed: bool,
    reputation_score: float,
    high_entropy_count: int,
) -> str:
    """Decide trust / review / reject from posture signals."""
    if not requires_auth or reputation_score < 25.0:
        return "reject"
    if code_signed and reputation_score >= 75.0 and high_entropy_count == 0:
        return "trust"
    return "review"
