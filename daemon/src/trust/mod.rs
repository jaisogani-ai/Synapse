// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

//! # Trust subsystem
//!
//! The [`ReputationStore`] tracks the trustworthiness of every agent, MCP, and
//! decision over time via a SQLite-backed reputation history. It is the daemon's
//! implementation of the Trust pillar.

pub mod reputation;

pub use reputation::ReputationMemory;

/// Errors returned by the trust subsystem.
#[derive(Debug, thiserror::Error)]
pub enum TrustError {
    /// A SQLite operation failed.
    #[error("sqlite error: {0}")]
    Sqlite(#[from] rusqlite::Error),

    /// JSON (de)serialization failed.
    #[error("serialization error: {0}")]
    Serde(#[from] serde_json::Error),

    /// Caller-supplied input was malformed or out of range.
    #[error("invalid input: {0}")]
    InvalidInput(String),
}

/// Convenience alias used throughout the trust subsystem.
pub type Result<T> = std::result::Result<T, TrustError>;

/// The trust subsystem behind one shareable handle.
///
/// `Send + Sync` so the IPC layer can share one `Arc<TrustStore>` across
/// tokio tasks. The reputation store manages its own interior `Mutex<Connection>`.
pub struct TrustStore {
    /// Agent/decision trustworthiness history (SQLite).
    pub reputation: ReputationMemory,
}

impl TrustStore {
    /// Build a fully in-memory trust store (tests + daemon default).
    pub fn new_in_memory() -> Result<Self> {
        Ok(Self {
            reputation: ReputationMemory::open_in_memory()?,
        })
    }
}
