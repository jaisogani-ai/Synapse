# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Synapse security subsystem (Python side).

- :mod:`synapse.security.capabilities` — capability authorization model.
- :mod:`synapse.security.zero_trust` — JWT/HMAC agent authentication.
- :mod:`synapse.security.supply_chain` — OSV + entropy supply-chain scanner.
- :mod:`synapse.security.secret_detector` — 140+ secret-type detector.
"""

from synapse.security.capabilities import (
    CAPABILITIES,
    Capability,
    CapabilityError,
    CapabilitySet,
)
from synapse.security.secret_detector import (
    SECRET_PATTERNS,
    SecretFinding,
    detect,
    has_secrets,
)
from synapse.security.supply_chain import (
    OsvClient,
    ScanReport,
    SupplyChainScanner,
    shannon_entropy,
)
from synapse.security.zero_trust import (
    AgentIdentity,
    Claims,
    VerificationResult,
    ZeroTrustNetwork,
)

__all__ = [
    "CAPABILITIES",
    "Capability",
    "CapabilityError",
    "CapabilitySet",
    "ZeroTrustNetwork",
    "AgentIdentity",
    "Claims",
    "VerificationResult",
    "SupplyChainScanner",
    "OsvClient",
    "ScanReport",
    "shannon_entropy",
    "SECRET_PATTERNS",
    "SecretFinding",
    "detect",
    "has_secrets",
]
