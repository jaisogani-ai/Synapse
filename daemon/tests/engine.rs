// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

//! Integration test for the trust store — proving the reputation subsystem
//! is shareable across threads behind `Arc<TrustStore>`.

use std::sync::Arc;

use synapse_daemon::trust::TrustStore;
use synapse_daemon::trust::reputation::Outcome;

#[test]
fn trust_store_boots_in_memory() {
    let store = TrustStore::new_in_memory().unwrap();
    store
        .reputation
        .record_outcome("agent", "d1", Outcome::Correct, "test", 1.0, "all")
        .unwrap();
    assert_eq!(store.reputation.get_reputation_score("agent", "all").unwrap(), 100.0);
}

#[test]
fn trust_store_is_shareable_across_threads() {
    let store = Arc::new(TrustStore::new_in_memory().unwrap());
    let mut handles = Vec::new();
    for i in 0..4 {
        let s = Arc::clone(&store);
        handles.push(std::thread::spawn(move || {
            s.reputation
                .record_outcome(&format!("agent-{i}"), "d", Outcome::Correct, "test", 1.0, "all")
                .unwrap();
        }));
    }
    for h in handles {
        h.join().unwrap();
    }
    let ranked = store.reputation.rank_agents("all").unwrap();
    assert!(ranked.len() >= 4);
}
