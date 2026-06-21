# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Unit tests for the supply-chain scanner (OSV + entropy)."""

from __future__ import annotations

from synapse.security.supply_chain import (
    OsvClient,
    SupplyChainScanner,
    shannon_entropy,
)


def test_shannon_entropy_extremes() -> None:
    assert shannon_entropy("") == 0.0
    assert shannon_entropy("aaaaaaaa") == 0.0
    assert shannon_entropy("ab") == 1.0
    assert shannon_entropy("abcdefgh") > shannon_entropy("aabbccdd")


def test_osv_client_parses_vulns_via_injected_fetcher() -> None:
    fake_response = {
        "vulns": [
            {"id": "GHSA-xxxx", "summary": "RCE", "severity": [{"score": "9.8"}]},
            {"id": "CVE-2026-1", "details": "info leak"},
        ]
    }
    client = OsvClient(fetcher=lambda url, body: fake_response)
    vulns = client.query_package("PyPI", "evil", "1.0.0")
    assert len(vulns) == 2
    assert vulns[0].id == "GHSA-xxxx"
    assert vulns[0].severity == "9.8"


def test_scan_package_rejects_when_vulnerable() -> None:
    osv = OsvClient(fetcher=lambda url, body: {"vulns": [{"id": "CVE-1", "summary": "bad"}]})
    scanner = SupplyChainScanner(osv=osv)
    report = scanner.scan_package("npm", "left-pad", "0.0.1")
    assert report.recommendation == "reject"
    assert len(report.known_cves) == 1


def test_scan_package_trusts_clean_dependency() -> None:
    osv = OsvClient(fetcher=lambda url, body: {"vulns": []})
    scanner = SupplyChainScanner(osv=osv)
    report = scanner.scan_package("npm", "safe-lib", "1.0.0")
    assert report.recommendation == "trust"


def test_scan_mcp_rejects_unauthenticated_server() -> None:
    scanner = SupplyChainScanner(osv=OsvClient(fetcher=lambda u, b: {"vulns": []}))
    report = scanner.scan_mcp_server("http://evil.local", requires_auth=False)
    assert report.recommendation == "reject"


def test_scan_mcp_trusts_signed_reputable_server() -> None:
    scanner = SupplyChainScanner(osv=OsvClient(fetcher=lambda u, b: {"vulns": []}))
    report = scanner.scan_mcp_server(
        "https://good.local",
        requires_auth=True,
        code_signed=True,
        reputation_score=90.0,
        manifest={"name": "good-mcp", "scripts": {"start": "node server.js"}},
    )
    assert report.recommendation == "trust"


def test_scan_mcp_flags_high_entropy_manifest() -> None:
    scanner = SupplyChainScanner(osv=OsvClient(fetcher=lambda u, b: {"vulns": []}))
    report = scanner.scan_mcp_server(
        "https://sketchy.local",
        requires_auth=True,
        code_signed=True,
        reputation_score=90.0,
        manifest={"postinstall": "aZ9bQ2xL7pR4tW1nK8mC3vB6dF0gH5jSxYz"},
    )
    assert report.high_entropy_findings
    assert report.recommendation == "review"  # entropy finding downgrades trust
