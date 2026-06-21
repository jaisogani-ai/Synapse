// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

//! # Synapse daemon library
//!
//! The privileged core of Synapse — identity, trust, reputation, and secure
//! secret handoff for AI agents. This crate exposes the core subsystems as a
//! library so they can be unit- and integration-tested, while the `synapsed`
//! binary wires them together into a running daemon.
//!
//! ## Subsystems
//!
//! - [`trust`] — the reputation store (who to trust, based on outcome history).
//! - [`protocol`] — Synapse Protocol v1.0 message types + JSON codec.
//! - [`ipc`] — the Unix-socket server (tokio async) that speaks the protocol.
//! - [`security`] — capability-based execution policies.

pub mod ipc;
pub mod protocol;
pub mod security;
pub mod trust;

pub use trust::TrustStore;
pub use protocol::{SynapseMessage, DEFAULT_MODEL, PROTOCOL_VERSION};
