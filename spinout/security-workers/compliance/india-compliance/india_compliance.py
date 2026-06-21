# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""India-specific compliance workers — first-class members of the worker fleet.

Five workers cover the regulations that matter most for Indian fintech and
data-handling products:

1. **DPDP Act 2023** — Digital Personal Data Protection Act.
2. **RBI AI Guidelines** — Reserve Bank of India directions on AI in finance.
3. **CERT-In Reporting** — 6-hour incident reporting rules.
4. **UPI Security** — NPCI/UPI payment safety.
5. **IT Act §43A** — reasonable security practices for sensitive data.

Each worker declares the checks it runs and the model it routes to (cheap/fast
Haiku for pattern-style checks; Opus for explainability reasoning). Phase 1
ships the worker definitions and a checklist-producing audit stub; the live
analysis is wired to the Security Agent fleet in a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Kept local (not imported from synapse-core) so this worker module can run
# standalone. Must stay consistent with synapse.router model ids.
OPUS = "claude-opus-4-8"
SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"
KNOWN_MODELS = frozenset({OPUS, SONNET, HAIKU})


@dataclass(frozen=True)
class ComplianceWorker:
    """A single, immutable India-compliance worker definition."""

    id: str
    regulation: str
    description: str
    checks: tuple[str, ...]
    model: str

    def __post_init__(self) -> None:
        """Validate the worker declaration at construction time."""
        if self.model not in KNOWN_MODELS:
            raise ValueError(
                f"worker {self.id!r}: unknown model {self.model!r}; "
                f"expected one of {sorted(KNOWN_MODELS)}"
            )
        if not self.checks:
            raise ValueError(f"worker {self.id!r}: must declare at least one check")


@dataclass(frozen=True)
class CheckResult:
    """The result of one compliance check (Phase 1: always ``pending``)."""

    check: str
    status: str = "pending"


@dataclass(frozen=True)
class AuditReport:
    """The output of running one worker's checklist."""

    worker_id: str
    regulation: str
    model: str
    items: tuple[CheckResult, ...] = field(default_factory=tuple)

    @property
    def total_checks(self) -> int:
        """Number of checks in this audit."""
        return len(self.items)


#: The five India-compliance workers, keyed by id.
INDIA_COMPLIANCE_WORKERS: dict[str, ComplianceWorker] = {
    "dpdp_act_2023": ComplianceWorker(
        id="dpdp_act_2023",
        regulation="Digital Personal Data Protection Act, 2023",
        description="Consent, fiduciary duties, cross-border transfer, erasure.",
        checks=(
            "Data Principal consent mechanisms",
            "Data Fiduciary obligations",
            "Cross-border data transfer restrictions",
            "Right to erasure implementation",
            "Grievance Redressal Officer requirement",
        ),
        model=HAIKU,  # fast, cheap, pattern-style checks
    ),
    "rbi_ai_guidelines": ComplianceWorker(
        id="rbi_ai_guidelines",
        regulation="RBI directions on AI in finance",
        description="Digital lending, model explainability, audit trails.",
        checks=(
            "RBI Master Direction on Digital Lending compliance",
            "AI model explainability for credit decisions",
            "Audit trail for AI-driven financial actions",
            "Customer consent for AI data processing",
        ),
        model=OPUS,  # explainability reasoning is complex
    ),
    "cert_in_reporting": ComplianceWorker(
        id="cert_in_reporting",
        regulation="CERT-In incident reporting rules",
        description="6-hour reporting window, breach notification, log retention.",
        checks=(
            "6-hour incident reporting window compliance",
            "Mandatory breach notification flow",
            "Log retention for 180 days requirement",
        ),
        model=HAIKU,
    ),
    "upi_security": ComplianceWorker(
        id="upi_security",
        regulation="NPCI / UPI security guidelines",
        description="UPI PIN handling, VPA validation, deep-link safety.",
        checks=(
            "UPI PIN never stored or logged",
            "NPCI security guidelines compliance",
            "VPA (Virtual Payment Address) validation",
            "UPI deep link security",
        ),
        model=HAIKU,
    ),
    "it_act_43a": ComplianceWorker(
        id="it_act_43a",
        regulation="IT Act, 2000 — §43A",
        description="Reasonable security practices for sensitive personal data.",
        checks=(
            "Reasonable security practices for sensitive data",
            "Compensation liability for data negligence",
        ),
        model=SONNET,
    ),
}


def all_worker_ids() -> list[str]:
    """Return the ids of all India-compliance workers."""
    return list(INDIA_COMPLIANCE_WORKERS)


def get_worker(worker_id: str) -> ComplianceWorker:
    """Return the worker for ``worker_id``.

    Raises:
        KeyError: if no such worker exists.
    """
    return INDIA_COMPLIANCE_WORKERS[worker_id]


def run_audit(worker_id: str) -> AuditReport:
    """Run a worker's checklist (Phase 1 stub: every item is ``pending``)."""
    worker = get_worker(worker_id)
    return AuditReport(
        worker_id=worker.id,
        regulation=worker.regulation,
        model=worker.model,
        items=tuple(CheckResult(check=c) for c in worker.checks),
    )
