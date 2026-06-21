// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

//! # Daemon security subsystem (Rust)
//!
//! Capability-based policy enforcement. The capability/zero-trust/supply-chain
//! logic lives in the Python SDK (`synapse.security.*`); the Rust side enforces
//! filesystem/command/network policies derived from granted capabilities.

pub mod capability;

pub use capability::{CapabilityError, CapabilityPolicy, NetworkPolicy};
