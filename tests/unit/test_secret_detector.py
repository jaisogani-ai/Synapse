# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Unit tests for the secret detector (140+ patterns + entropy).

The fixtures below match the production detector's regexes but are constructed
at runtime by string concatenation so the literal prefixes (``sk_live_``,
``ghp_``, ``sk-ant-``, ``AKIA``…) never appear as contiguous string literals
in this source file. That keeps third-party scanners (e.g. GitHub Push
Protection) from flagging this file as a leaked-credential source.
"""

from __future__ import annotations

from synapse.security.secret_detector import (
    SECRET_PATTERNS,
    detect,
    has_secrets,
    redact,
)

# Fixtures: assembled at runtime so the recognizable prefix is never a
# contiguous literal in source. These are NOT real credentials.
_AWS_FIXTURE = "AKIA" + "IOSFODNN7EXAMPLE"
_GH_FIXTURE = "ghp" + "_" + "0123456789abcdefghijklmnopqrstuvwxyz"
_ANTHROPIC_FIXTURE = "sk-ant-" + "api03-" + "abcdefghijklmnopqrstuvwxyz0123"
_STRIPE_FIXTURE = "sk_" + "live_" + "0123456789abcdefghijklmno"


def test_catalog_has_at_least_140_patterns() -> None:
    assert len(SECRET_PATTERNS) >= 140
    # Pattern names are unique.
    names = [p.name for p in SECRET_PATTERNS]
    assert len(names) == len(set(names))


def test_detects_common_provider_secrets() -> None:
    content = "\n".join(
        [
            f"aws_key = {_AWS_FIXTURE}",
            f"gh = {_GH_FIXTURE}",
            f"anthropic = {_ANTHROPIC_FIXTURE}",
            f"stripe = {_STRIPE_FIXTURE}",
            "-----BEGIN RSA PRIVATE KEY-----",
        ]
    )
    providers = {f.provider for f in detect(content, include_entropy=False)}
    assert {"AWS", "GitHub", "Anthropic", "Stripe", "Crypto"} <= providers


def test_findings_are_redacted() -> None:
    secret = _GH_FIXTURE
    findings = detect(f"token={secret}", include_entropy=False)
    assert findings
    for finding in findings:
        assert secret not in finding.preview
    assert "[redacted" in redact(secret)


def test_has_secrets_true_and_false() -> None:
    assert has_secrets(f"key={_AWS_FIXTURE}")
    assert not has_secrets("just some ordinary text with no secrets")


def test_entropy_fallback_flags_unknown_high_entropy_token() -> None:
    findings = detect("blob: aZ9bQ2xL7pR4tW1nK8mC3vB6dF0gH5jSxYz", include_entropy=True)
    assert any(f.name == "High-Entropy String" for f in findings)


def test_line_numbers_are_reported() -> None:
    content = f"clean line\nkey = {_AWS_FIXTURE}\nanother clean line"
    findings = detect(content, include_entropy=False)
    assert any(f.line == 2 for f in findings)
