# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Continuous Verifier — the labelled orchestrator for the three-gate trust model.

This module gives a name to what the receiver already does: every inbound
A2A message passes through Gate 1 (signature + timestamp), Gate 2
(reputation), and Gate 3 (capability) before any side effect happens. The
:class:`ContinuousVerifier` class wraps those gate decisions into one
testable surface so we can talk about "continuous verification" in the
docs without that being a vague claim — it is exactly this function call
sequence, on every message, with no implicit skips.

The verifier itself does not own the gate implementations. It composes:

  * Gate 1 → :class:`A2ASigner` (HMAC + timestamp)
  * Gate 2 → :class:`TrustStore` (reputation score lookup)
  * Gate 3 → :class:`ZeroTrustNetwork.verify_request` (token + capability)
  * Bonus  → :class:`QuarantineStore` (auto-block lookup)

so the unit tests for this module verify ordering and short-circuit
behaviour, not crypto correctness (that's tested in the constituent
modules).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

#: The gates, in the order the receiver enforces them.
GATES = ("quarantine", "signature", "reputation", "capability")


@dataclass(frozen=True)
class GateResult:
    """One gate's outcome."""

    gate: str
    ok: bool
    reason: str = ""


@dataclass(frozen=True)
class VerificationResult:
    """The full set of gate outcomes for one message."""

    ok: bool
    failed_gate: str = ""
    reason: str = ""
    gate_results: tuple[GateResult, ...] = ()


GateFn = Callable[[], GateResult]


def verify(*gate_callables: GateFn) -> VerificationResult:
    """Run each gate in order, short-circuiting on the first failure.

    Each callable returns its own :class:`GateResult`. The receiver wires
    these closures around the real signer / trust store / network / quarantine
    store; this function just enforces order + short-circuit semantics so we
    can write one test for "all gates run, in this order, no implicit skip".
    """
    results: list[GateResult] = []
    for gate_fn in gate_callables:
        r = gate_fn()
        results.append(r)
        if not r.ok:
            return VerificationResult(
                ok=False,
                failed_gate=r.gate,
                reason=r.reason,
                gate_results=tuple(results),
            )
    return VerificationResult(
        ok=True,
        gate_results=tuple(results),
    )
