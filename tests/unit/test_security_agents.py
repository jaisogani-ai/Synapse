# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Tests for the v0.1.0-alpha security primitives that the diagrams label
"Quarantine & Isolation", "Threat Response", "Anomaly Detection",
"Access Review", "Device Identity (DID)", and "Continuous Verification".

Each module is small and contained; the tests pin its public contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from synapse.security.access_review import AccessReport, review
from synapse.security.anomaly import (
    DEFAULT_Z_THRESHOLD,
    AnomalyResult,
    RateAnomalyDetector,
)
from synapse.security.continuous_verifier import (
    GATES,
    GateResult,
    VerificationResult,
    verify,
)
from synapse.security.device_identity import (
    DID_PREFIX,
    DeviceIdentity,
    DeviceIdentityError,
    make_did,
    parse_did,
)
from synapse.security.quarantine import (
    DEFAULT_QUARANTINE_THRESHOLD,
    QuarantineStore,
    should_quarantine,
)
from synapse.security.threat_response import (
    MAX_CONSECUTIVE_FAILURES,
    FailureTracker,
)


# ─── 1. Quarantine ──────────────────────────────────────────────────────────


def test_should_quarantine_threshold_default() -> None:
    assert should_quarantine(0.0)
    assert should_quarantine(DEFAULT_QUARANTINE_THRESHOLD)
    assert not should_quarantine(0.11)


def test_quarantine_store_round_trip(tmp_path: Path) -> None:
    store = QuarantineStore(tmp_path / "q.json")
    assert not store.is_quarantined("alice")
    store.quarantine("alice", reason="rep<=0.1", at="2026-06-22T00:00:00Z")
    assert store.is_quarantined("alice")
    assert [e.agent_id for e in store.list_all()] == ["alice"]


def test_quarantine_release_returns_true_only_when_changed(tmp_path: Path) -> None:
    store = QuarantineStore(tmp_path / "q.json")
    store.quarantine("alice", reason="manual", at="2026-06-22T00:00:00Z")
    assert store.release("alice") is True
    assert store.release("alice") is False  # already released
    assert not store.is_quarantined("alice")


def test_quarantine_store_survives_process_restart(tmp_path: Path) -> None:
    path = tmp_path / "q.json"
    QuarantineStore(path).quarantine("evil", "test", "2026-06-22T00:00:00Z")
    # New instance — must re-read from disk.
    fresh = QuarantineStore(path)
    assert fresh.is_quarantined("evil")


# ─── 2. Threat Response ────────────────────────────────────────────────────


def test_failure_tracker_increments_then_blocks() -> None:
    tracker = FailureTracker(max_consecutive=3)
    assert not tracker.should_block("alice")
    tracker.record_failure("alice")
    tracker.record_failure("alice")
    assert not tracker.should_block("alice")
    tracker.record_failure("alice")
    assert tracker.should_block("alice")
    assert tracker.count_for("alice") == 3


def test_failure_tracker_success_resets() -> None:
    tracker = FailureTracker(max_consecutive=3)
    for _ in range(2):
        tracker.record_failure("alice")
    tracker.record_success("alice")
    assert tracker.count_for("alice") == 0
    assert not tracker.should_block("alice")


def test_failure_tracker_per_agent_isolation() -> None:
    tracker = FailureTracker(max_consecutive=3)
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        tracker.record_failure("evil")
    assert tracker.should_block("evil")
    assert not tracker.should_block("alice")  # different agent untouched


# ─── 3. Anomaly Detection ──────────────────────────────────────────────────


def test_anomaly_detector_quiet_period_is_not_flagged() -> None:
    detector = RateAnomalyDetector()
    for i in range(10):
        result = detector.observe("alice", now=1_750_000_000 + i)
        assert isinstance(result, AnomalyResult)
        assert not result.is_anomaly


def test_anomaly_detector_burst_is_flagged() -> None:
    detector = RateAnomalyDetector(window_seconds=60, z_threshold=DEFAULT_Z_THRESHOLD)
    # 10 seconds of low rate (one msg per second)
    for i in range(10):
        detector.observe("alice", now=1_750_000_000 + i)
    # Burst — 30 messages in the same second
    result = AnomalyResult(False, 0.0, 0.0, 0.0, 0.0)
    for _ in range(30):
        result = detector.observe("alice", now=1_750_000_020)
    assert result.is_anomaly
    assert result.z_score >= DEFAULT_Z_THRESHOLD


def test_anomaly_detector_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        RateAnomalyDetector(window_seconds=1)
    with pytest.raises(ValueError):
        RateAnomalyDetector(z_threshold=0)


def test_anomaly_detector_per_agent_isolation() -> None:
    detector = RateAnomalyDetector()
    for i in range(10):
        detector.observe("quiet-agent", now=1_750_000_000 + i)
    # Burst from a different agent should not be measured against the quiet one
    for _ in range(50):
        detector.observe("noisy-agent", now=1_750_000_100)
    # And the quiet one's history is unchanged
    result = detector.observe("quiet-agent", now=1_750_000_100)
    assert not result.is_anomaly


# ─── 4. Access Review ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class _StubEntry:
    """Stub matching the AuditEntry shape Access Review needs."""

    action: str
    sender: str
    receiver: str
    timestamp: str


def test_access_review_counts_by_action_sender_receiver() -> None:
    entries = [
        _StubEntry("send_task", "alice", "bob", "2026-06-22T10:00:00Z"),
        _StubEntry("send_task", "alice", "bob", "2026-06-22T10:01:00Z"),
        _StubEntry("receive_task", "alice", "bob", "2026-06-22T10:01:01Z"),
        _StubEntry("reject_capability", "evil", "bob", "2026-06-22T10:02:00Z"),
    ]
    report = review(entries)
    assert isinstance(report, AccessReport)
    assert report.total_entries == 4
    assert report.by_action == {
        "send_task": 2,
        "receive_task": 1,
        "reject_capability": 1,
    }
    senders = {a.agent_id: a.total for a in report.by_sender}
    assert senders == {"alice": 3, "evil": 1}
    assert {a.agent_id for a in report.by_receiver} == {"bob"}


def test_access_review_window_filter() -> None:
    entries = [
        _StubEntry("send_task", "alice", "bob", "2026-06-22T10:00:00Z"),
        _StubEntry("send_task", "alice", "bob", "2026-06-22T12:00:00Z"),
        _StubEntry("send_task", "alice", "bob", "2026-06-23T00:00:00Z"),
    ]
    report = review(
        entries,
        window_from="2026-06-22T11:00:00Z",
        window_to="2026-06-22T23:59:59Z",
    )
    assert report.total_entries == 1


# ─── 5. Device Identity ───────────────────────────────────────────────────


def test_make_and_parse_did_round_trip() -> None:
    did = make_did("alice", device_id="laptop-7")
    assert did == "did:synapse:alice#laptop-7"
    parsed = parse_did(did)
    assert isinstance(parsed, DeviceIdentity)
    assert parsed.agent_id == "alice"
    assert parsed.device_id == "laptop-7"


def test_did_without_device_id() -> None:
    did = make_did("alice")
    assert did == f"{DID_PREFIX}alice"
    assert parse_did(did).device_id == ""


def test_did_rejects_invalid_inputs() -> None:
    with pytest.raises(DeviceIdentityError):
        parse_did("not-a-did")
    with pytest.raises(DeviceIdentityError):
        parse_did("did:other:alice")
    with pytest.raises(DeviceIdentityError):
        make_did("UPPER")  # uppercase not allowed
    with pytest.raises(DeviceIdentityError):
        make_did("a", device_id="bad chars")


# ─── 6. Continuous Verifier ────────────────────────────────────────────────


def test_continuous_verifier_runs_all_gates_in_order_on_clean_path() -> None:
    seen: list[str] = []

    def g1() -> GateResult:
        seen.append("signature")
        return GateResult("signature", True)

    def g2() -> GateResult:
        seen.append("reputation")
        return GateResult("reputation", True)

    def g3() -> GateResult:
        seen.append("capability")
        return GateResult("capability", True)

    result = verify(g1, g2, g3)
    assert isinstance(result, VerificationResult)
    assert result.ok
    assert seen == ["signature", "reputation", "capability"]
    assert len(result.gate_results) == 3


def test_continuous_verifier_short_circuits_on_first_failure() -> None:
    seen: list[str] = []

    def g1() -> GateResult:
        seen.append("g1")
        return GateResult("signature", True)

    def g2() -> GateResult:
        seen.append("g2")
        return GateResult("reputation", False, reason="rep too low")

    def g3() -> GateResult:
        seen.append("g3")  # must not be called
        return GateResult("capability", True)

    result = verify(g1, g2, g3)
    assert not result.ok
    assert result.failed_gate == "reputation"
    assert result.reason == "rep too low"
    assert seen == ["g1", "g2"]


def test_continuous_verifier_documented_gate_order() -> None:
    assert GATES == ("quarantine", "signature", "reputation", "capability")
