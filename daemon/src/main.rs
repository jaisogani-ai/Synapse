// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

//! # `synapsed` — the Synapse daemon
//!
//! The privileged core of Synapse — identity, trust, reputation, and secure
//! secret handoff for AI agents. On boot it:
//!
//! 1. initializes structured tracing,
//! 2. constructs the in-memory trust store,
//! 3. listens on a Unix socket and serves the
//!    [Synapse Protocol](synapse_daemon::protocol) until `Ctrl-C`.
//!
//! The socket path comes from `SYNAPSE_SOCKET`, defaulting to
//! `<tmp>/synapse.sock`.

use std::sync::Arc;

use synapse_daemon::ipc;
use synapse_daemon::trust::TrustStore;
use synapse_daemon::protocol::{DEFAULT_MODEL, PROTOCOL_VERSION};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    init_tracing();

    let socket_path = std::env::var("SYNAPSE_SOCKET").unwrap_or_else(|_| default_socket_path());
    let store = Arc::new(TrustStore::new_in_memory()?);

    print_banner(&socket_path);

    tokio::select! {
        result = ipc::serve(&socket_path, Arc::clone(&store)) => {
            if let Err(e) = result {
                tracing::error!("IPC server stopped with error: {e}");
                return Err(e);
            }
        }
        _ = tokio::signal::ctrl_c() => {
            tracing::info!("shutdown signal received; stopping Synapse daemon");
        }
    }

    let _ = std::fs::remove_file(&socket_path);
    Ok(())
}

fn default_socket_path() -> String {
    std::env::temp_dir()
        .join("synapse.sock")
        .to_string_lossy()
        .into_owned()
}

fn init_tracing() {
    use tracing_subscriber::EnvFilter;
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(false)
        .init();
}

fn print_banner(socket_path: &str) {
    tracing::info!("Synapse daemon (synapsed) v{}", env!("CARGO_PKG_VERSION"));
    tracing::info!("   protocol  : v{PROTOCOL_VERSION}");
    tracing::info!("   model     : {DEFAULT_MODEL}");
    tracing::info!("   subsystems: trust");
    tracing::info!("   socket    : {socket_path}");
}
