// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

//! Integration tests for the **Reputation store** (who to trust).

use synapse_daemon::trust::reputation::{Outcome, ReputationMemory};

#[test]
fn ranks_agents_by_track_record() {
    let rm = ReputationMemory::open_in_memory().unwrap();
    for i in 0..5 {
        rm.record_outcome("sentinel", &format!("d{i}"), Outcome::Correct, "test", 1.0, "security")
            .unwrap();
    }
    rm.record_outcome("rookie", "d0", Outcome::Correct, "test", 1.0, "security").unwrap();
    rm.record_outcome("rookie", "d1", Outcome::Incorrect, "human", 1.0, "security").unwrap();
    rm.record_outcome("rookie", "d2", Outcome::Incorrect, "human", 1.0, "security").unwrap();

    let ranked = rm.rank_agents("security").unwrap();
    assert_eq!(ranked[0].0, "sentinel");
    assert!(ranked[0].1 > ranked[1].1);
    assert_eq!(ranked[0].1, 100.0);
}

#[test]
fn should_trust_uses_threshold_and_history() {
    let rm = ReputationMemory::open_in_memory().unwrap();
    rm.record_outcome("verdict", "d0", Outcome::Correct, "production_metric", 0.9, "verdict")
        .unwrap();

    let (trust, reason) = rm.should_trust("verdict", "verdict").unwrap();
    assert!(trust, "reason: {reason}");

    let (no_trust, reason) = rm.should_trust("unknown-agent", "verdict").unwrap();
    assert!(!no_trust);
    assert!(reason.contains("no track record"));
}

#[test]
fn partial_outcomes_count_as_half() {
    let rm = ReputationMemory::open_in_memory().unwrap();
    rm.record_outcome("a", "d0", Outcome::Partial, "human", 1.0, "x").unwrap();
    let score = rm.get_reputation_score("a", "x").unwrap();
    assert!((score - 50.0).abs() < 1e-6);
}
