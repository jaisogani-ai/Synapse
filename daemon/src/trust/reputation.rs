// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

//! # Reputation store — the Trust pillar
//!
//! Tracks the trustworthiness of every agent, MCP, and decision over time.
//! Backed by SQLite.
//!
//! Each recorded [`Outcome`] is weighted by the caller's `confidence`
//! (`0.0..=1.0`). A reputation score is the confidence-weighted fraction of
//! good outcomes, scaled to `0..=100`:
//!
//! - `Correct` counts as `1.0`, `Partial` as `0.5`, `Incorrect` as `0.0`.
//! - `Unknown` outcomes are ignored (no signal).
//! - With no signal, the score is a neutral `50.0`.

use std::collections::BTreeSet;
use std::sync::Mutex;

use rusqlite::Connection;
use serde::{Deserialize, Serialize};

use super::{TrustError, Result};

/// The score returned when there is no usable history.
pub const NEUTRAL_SCORE: f64 = 50.0;
/// Minimum score for [`ReputationMemory::should_trust`] to return `true`.
pub const TRUST_THRESHOLD: f64 = 60.0;

/// The observed result of a decision/action.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Outcome {
    /// The decision proved correct.
    Correct,
    /// The decision proved incorrect.
    Incorrect,
    /// The decision was partially correct.
    Partial,
    /// The result could not be determined.
    Unknown,
}

impl Outcome {
    /// Canonical storage string.
    pub fn as_str(&self) -> &'static str {
        match self {
            Outcome::Correct => "correct",
            Outcome::Incorrect => "incorrect",
            Outcome::Partial => "partial",
            Outcome::Unknown => "unknown",
        }
    }

    /// Parse from a stored string.
    pub fn parse(s: &str) -> Result<Self> {
        match s.to_ascii_lowercase().as_str() {
            "correct" => Ok(Outcome::Correct),
            "incorrect" => Ok(Outcome::Incorrect),
            "partial" => Ok(Outcome::Partial),
            "unknown" => Ok(Outcome::Unknown),
            other => Err(TrustError::InvalidInput(format!("unknown outcome: {other}"))),
        }
    }

    /// Quality weight in `[0, 1]`; `None` for [`Outcome::Unknown`] (no signal).
    fn quality(&self) -> Option<f64> {
        match self {
            Outcome::Correct => Some(1.0),
            Outcome::Partial => Some(0.5),
            Outcome::Incorrect => Some(0.0),
            Outcome::Unknown => None,
        }
    }
}

/// T8 reputation memory backed by SQLite.
#[derive(Debug)]
pub struct ReputationMemory {
    conn: Mutex<Connection>,
}

impl ReputationMemory {
    /// Open (or create) a reputation store at `path`.
    pub fn open(path: impl AsRef<std::path::Path>) -> Result<Self> {
        Self::from_connection(Connection::open(path)?)
    }

    /// Open an in-memory reputation store (tests + Phase 1 daemon).
    pub fn open_in_memory() -> Result<Self> {
        Self::from_connection(Connection::open_in_memory()?)
    }

    fn from_connection(conn: Connection) -> Result<Self> {
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS reputation_outcomes (
                 id              INTEGER PRIMARY KEY AUTOINCREMENT,
                 agent_id        TEXT NOT NULL,
                 decision_id     TEXT NOT NULL,
                 outcome         TEXT NOT NULL,
                 feedback_source TEXT NOT NULL,
                 confidence      REAL NOT NULL,
                 domain          TEXT NOT NULL,
                 created_at      TEXT NOT NULL
             );
             CREATE INDEX IF NOT EXISTS idx_rep_agent ON reputation_outcomes(agent_id);
             CREATE INDEX IF NOT EXISTS idx_rep_domain ON reputation_outcomes(domain);",
        )?;
        Ok(Self {
            conn: Mutex::new(conn),
        })
    }

    /// Record an outcome for `agent_id` on `decision_id`.
    ///
    /// # Errors
    /// [`TrustError::InvalidInput`] if `confidence` is outside `0.0..=1.0`.
    pub fn record_outcome(
        &self,
        agent_id: &str,
        decision_id: &str,
        outcome: Outcome,
        feedback_source: &str,
        confidence: f64,
        domain: &str,
    ) -> Result<()> {
        if !(0.0..=1.0).contains(&confidence) {
            return Err(TrustError::InvalidInput(format!(
                "confidence {confidence} out of range 0.0..=1.0"
            )));
        }
        if agent_id.is_empty() {
            return Err(TrustError::InvalidInput("agent_id is empty".into()));
        }
        let domain = if domain.is_empty() { "all" } else { domain };
        let created_at = chrono::Utc::now().to_rfc3339();
        let conn = self.lock();
        conn.execute(
            "INSERT INTO reputation_outcomes
                (agent_id, decision_id, outcome, feedback_source, confidence, domain, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            (
                agent_id,
                decision_id,
                outcome.as_str(),
                feedback_source,
                confidence,
                domain,
                &created_at,
            ),
        )?;
        Ok(())
    }

    /// Confidence-weighted reputation score for `agent_id` in `domain`
    /// (use `"all"` for every domain). Returns `0.0..=100.0`.
    pub fn get_reputation_score(&self, agent_id: &str, domain: &str) -> Result<f64> {
        let rows = self.weighted_outcomes(Some(agent_id), domain)?;
        Ok(score_from(&rows))
    }

    /// Number of recorded outcomes for `agent_id` in `domain`.
    pub fn outcome_count(&self, agent_id: &str, domain: &str) -> Result<usize> {
        Ok(self.weighted_outcomes(Some(agent_id), domain)?.len())
    }

    /// All agents ranked by reputation in `domain`, best first.
    pub fn rank_agents(&self, domain: &str) -> Result<Vec<(String, f64)>> {
        let mut agents = BTreeSet::new();
        {
            let conn = self.lock();
            if domain == "all" {
                let mut stmt =
                    conn.prepare("SELECT DISTINCT agent_id FROM reputation_outcomes")?;
                let mut rows = stmt.query([])?;
                while let Some(row) = rows.next()? {
                    agents.insert(row.get::<_, String>(0)?);
                }
            } else {
                let mut stmt = conn.prepare(
                    "SELECT DISTINCT agent_id FROM reputation_outcomes WHERE domain = ?1",
                )?;
                let mut rows = stmt.query([domain])?;
                while let Some(row) = rows.next()? {
                    agents.insert(row.get::<_, String>(0)?);
                }
            }
        }
        let mut ranked: Vec<(String, f64)> = Vec::with_capacity(agents.len());
        for agent in agents {
            let score = self.get_reputation_score(&agent, domain)?;
            ranked.push((agent, score));
        }
        ranked.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        Ok(ranked)
    }

    /// Whether `agent_id` should be trusted for `domain`, with a reason.
    ///
    /// Falls back to the `"all"` domain when there is no domain-specific
    /// history. Trust requires both a track record and a score at or above
    /// [`TRUST_THRESHOLD`].
    pub fn should_trust(&self, agent_id: &str, domain: &str) -> Result<(bool, String)> {
        let mut effective_domain = domain.to_string();
        let mut count = self.outcome_count(agent_id, domain)?;
        if count == 0 && domain != "all" {
            effective_domain = "all".to_string();
            count = self.outcome_count(agent_id, "all")?;
        }
        let score = self.get_reputation_score(agent_id, &effective_domain)?;

        if count == 0 {
            return Ok((
                false,
                format!("no track record for '{agent_id}' (neutral score {NEUTRAL_SCORE})"),
            ));
        }
        let trust = score >= TRUST_THRESHOLD;
        let reason = format!(
            "score {score:.1} from {count} outcome(s) in '{effective_domain}' \
             (threshold {TRUST_THRESHOLD})"
        );
        Ok((trust, reason))
    }

    fn weighted_outcomes(
        &self,
        agent_id: Option<&str>,
        domain: &str,
    ) -> Result<Vec<(Outcome, f64)>> {
        let conn = self.lock();
        // Collect raw rows first (so the prepared statement's borrow ends before
        // we parse), then convert outcome strings to the typed enum.
        let raw: Vec<(String, f64)> = match (agent_id, domain) {
            (Some(agent), "all") => {
                let mut stmt = conn.prepare(
                    "SELECT outcome, confidence FROM reputation_outcomes WHERE agent_id = ?1",
                )?;
                let rows = stmt.query_map([agent], map_outcome_row)?;
                drain(rows)?
            }
            (Some(agent), dom) => {
                let mut stmt = conn.prepare(
                    "SELECT outcome, confidence FROM reputation_outcomes \
                     WHERE agent_id = ?1 AND domain = ?2",
                )?;
                let rows = stmt.query_map([agent, dom], map_outcome_row)?;
                drain(rows)?
            }
            (None, "all") => {
                let mut stmt =
                    conn.prepare("SELECT outcome, confidence FROM reputation_outcomes")?;
                let rows = stmt.query_map([], map_outcome_row)?;
                drain(rows)?
            }
            (None, dom) => {
                let mut stmt = conn.prepare(
                    "SELECT outcome, confidence FROM reputation_outcomes WHERE domain = ?1",
                )?;
                let rows = stmt.query_map([dom], map_outcome_row)?;
                drain(rows)?
            }
        };

        let mut out = Vec::with_capacity(raw.len());
        for (outcome, confidence) in raw {
            out.push((Outcome::parse(&outcome)?, confidence));
        }
        Ok(out)
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, Connection> {
        self.conn.lock().expect("reputation connection mutex poisoned")
    }
}

/// Map a SQL row to `(outcome_string, confidence)`.
fn map_outcome_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<(String, f64)> {
    Ok((row.get(0)?, row.get(1)?))
}

/// Collect a `query_map` iterator into a `Vec`, propagating the first error.
fn drain(
    rows: impl Iterator<Item = rusqlite::Result<(String, f64)>>,
) -> Result<Vec<(String, f64)>> {
    let mut out = Vec::new();
    for row in rows {
        out.push(row?);
    }
    Ok(out)
}

/// Compute a `0..=100` score from `(outcome, confidence)` pairs.
fn score_from(rows: &[(Outcome, f64)]) -> f64 {
    let mut weighted_value = 0.0;
    let mut total_weight = 0.0;
    for (outcome, confidence) in rows {
        if let Some(quality) = outcome.quality() {
            weighted_value += quality * confidence;
            total_weight += confidence;
        }
    }
    if total_weight == 0.0 {
        NEUTRAL_SCORE
    } else {
        (weighted_value / total_weight) * 100.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn neutral_score_without_history() {
        let rm = ReputationMemory::open_in_memory().unwrap();
        assert_eq!(rm.get_reputation_score("ghost", "all").unwrap(), NEUTRAL_SCORE);
    }

    #[test]
    fn correct_outcomes_raise_score() {
        let rm = ReputationMemory::open_in_memory().unwrap();
        rm.record_outcome("sec", "d1", Outcome::Correct, "human", 1.0, "security")
            .unwrap();
        rm.record_outcome("sec", "d2", Outcome::Correct, "test", 1.0, "security")
            .unwrap();
        assert_eq!(rm.get_reputation_score("sec", "security").unwrap(), 100.0);
    }

    #[test]
    fn incorrect_outcomes_lower_score() {
        let rm = ReputationMemory::open_in_memory().unwrap();
        rm.record_outcome("a", "d1", Outcome::Correct, "human", 1.0, "x").unwrap();
        rm.record_outcome("a", "d2", Outcome::Incorrect, "human", 1.0, "x").unwrap();
        assert!((rm.get_reputation_score("a", "x").unwrap() - 50.0).abs() < 1e-6);
    }

    #[test]
    fn unknown_outcomes_are_ignored() {
        let rm = ReputationMemory::open_in_memory().unwrap();
        rm.record_outcome("a", "d1", Outcome::Unknown, "agent", 1.0, "x").unwrap();
        assert_eq!(rm.get_reputation_score("a", "x").unwrap(), NEUTRAL_SCORE);
    }

    #[test]
    fn ranks_agents_best_first() {
        let rm = ReputationMemory::open_in_memory().unwrap();
        rm.record_outcome("good", "d", Outcome::Correct, "human", 1.0, "dom").unwrap();
        rm.record_outcome("bad", "d", Outcome::Incorrect, "human", 1.0, "dom").unwrap();
        let ranked = rm.rank_agents("dom").unwrap();
        assert_eq!(ranked[0].0, "good");
        assert_eq!(ranked[1].0, "bad");
    }

    #[test]
    fn should_trust_respects_threshold() {
        let rm = ReputationMemory::open_in_memory().unwrap();
        rm.record_outcome("trusty", "d", Outcome::Correct, "human", 1.0, "dom").unwrap();
        let (trust, _) = rm.should_trust("trusty", "dom").unwrap();
        assert!(trust);

        let (no_trust, reason) = rm.should_trust("stranger", "dom").unwrap();
        assert!(!no_trust);
        assert!(reason.contains("no track record"));
    }

    #[test]
    fn rejects_out_of_range_confidence() {
        let rm = ReputationMemory::open_in_memory().unwrap();
        assert!(matches!(
            rm.record_outcome("a", "d", Outcome::Correct, "human", 1.5, "x").unwrap_err(),
            TrustError::InvalidInput(_)
        ));
    }
}
