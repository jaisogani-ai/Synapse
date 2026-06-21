# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Unit tests for the capability authorization system."""

from __future__ import annotations

import pytest

from synapse.security.capabilities import (
    CAPABILITIES,
    CapabilityError,
    CapabilitySet,
    is_known,
    validate,
)


def test_exact_grant_allows_only_that_capability() -> None:
    caps = CapabilitySet.of("trust.read")
    assert caps.allows("trust.read")
    assert not caps.allows("trust.write")


def test_namespace_wildcard_grants_all_actions() -> None:
    caps = CapabilitySet.of("trust.*")
    assert caps.allows("trust.read")
    assert caps.allows("trust.write")
    assert not caps.allows("vault.rotate")


def test_global_wildcard_grants_everything() -> None:
    caps = CapabilitySet.of("*")
    assert caps.allows("vault.revoke")
    assert caps.allows("trust.admin")


def test_grant_and_revoke_are_immutable() -> None:
    base = CapabilitySet.of("trust.read")
    granted = base.grant("vault.audit")
    revoked = granted.revoke("trust.read")
    # Original is untouched (immutability rule).
    assert base.to_sorted_list() == ["trust.read"]
    assert granted.allows("vault.audit")
    assert not revoked.allows("trust.read")


def test_invalid_capability_string_is_rejected() -> None:
    with pytest.raises(CapabilityError):
        validate("MemoryRead")  # not namespace.action
    with pytest.raises(CapabilityError):
        CapabilitySet.of("bad capability")


def test_registry_lookup() -> None:
    assert is_known("vault.request_credential")
    assert not is_known("nonexistent.capability")
    assert len(CAPABILITIES) >= 20
