// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

//! # IPC — the Unix-socket server
//!
//! The daemon's front door. It listens on a Unix domain socket and speaks the
//! [Synapse Protocol](crate::protocol): newline-delimited JSON
//! [`SynapseMessage`]s, one request per line, one response per line.
//!
//! Each accepted connection is handled on its own tokio task and shares a
//! single `Arc<TrustStore>`. The dispatch logic ([`dispatch`]) is a pure
//! function of `(store, raw_line)`, which makes it directly unit-testable
//! without a socket.

use std::path::Path;
use std::sync::Arc;

use serde_json::json;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{UnixListener, UnixStream};

use crate::security::capability::is_granted;
use crate::trust::{TrustError, TrustStore};
use crate::protocol::{
    error_code, Body, TrustOp, RequestBody, SynapseMessage, DEFAULT_MODEL,
    PROTOCOL_VERSION,
};
use crate::trust::reputation::Outcome;

/// Required capability per [`TrustOp`] variant. Consulted by [`dispatch`]
/// before any mutation. Read ops require `trust.read`; writes require
/// `trust.write`.
fn required_capability_for(op: &TrustOp) -> &'static str {
    match op {
        TrustOp::RecordOutcome { .. } => "trust.write",
        TrustOp::GetScore { .. } => "trust.read",
        TrustOp::ShouldTrust { .. } => "trust.read",
        TrustOp::RankAgents { .. } => "trust.read",
    }
}

/// The sender id the daemon uses on its own messages.
pub const DAEMON_SENDER: &str = "synapse-daemon";

/// Bind a Unix socket at `socket_path` and serve forever.
pub async fn serve(socket_path: impl AsRef<Path>, store: Arc<TrustStore>) -> anyhow::Result<()> {
    let path = socket_path.as_ref();
    if path.exists() {
        let _ = std::fs::remove_file(path);
    }
    let listener = UnixListener::bind(path)?;
    tracing::info!(socket = %path.display(), "Synapse IPC server listening");

    loop {
        let (stream, _addr) = listener.accept().await?;
        let s = Arc::clone(&store);
        tokio::spawn(async move {
            if let Err(e) = handle_connection(stream, s).await {
                tracing::warn!("connection handler error: {e}");
            }
        });
    }
}

async fn handle_connection(stream: UnixStream, store: Arc<TrustStore>) -> anyhow::Result<()> {
    let (read_half, mut write_half) = stream.into_split();
    let mut reader = BufReader::new(read_half);
    let mut line = String::new();

    loop {
        line.clear();
        let bytes = reader.read_line(&mut line).await?;
        if bytes == 0 {
            break;
        }
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let response = dispatch(&store, trimmed);
        let mut out = response
            .to_json()
            .unwrap_or_else(|_| FALLBACK_ERROR_JSON.to_string());
        out.push('\n');
        write_half.write_all(out.as_bytes()).await?;
        write_half.flush().await?;
    }
    Ok(())
}

const FALLBACK_ERROR_JSON: &str =
    r#"{"id":"0","version":"1.0","timestamp":"1970-01-01T00:00:00Z","sender":"synapse-daemon","body":{"response":{"error":{"code":"internal","message":"response serialization failed"}}}}"#;

/// Parse `raw` as a [`SynapseMessage`] and produce the response message.
pub fn dispatch(store: &TrustStore, raw: &str) -> SynapseMessage {
    let msg = match SynapseMessage::from_json(raw) {
        Ok(m) => m,
        Err(e) => {
            return SynapseMessage::error(
                DAEMON_SENDER,
                error_code::BAD_REQUEST,
                format!("invalid message: {e}"),
            )
        }
    };

    if !msg.is_supported_version() {
        return SynapseMessage::error(
            DAEMON_SENDER,
            error_code::UNSUPPORTED_VERSION,
            format!("unsupported protocol version: {}", msg.version),
        );
    }

    let caps = msg.caps.clone();
    match msg.body {
        Body::Request(req) => handle_request(store, &caps, req),
        _ => SynapseMessage::error(
            DAEMON_SENDER,
            error_code::BAD_REQUEST,
            "expected a request body",
        ),
    }
}

fn handle_request(
    store: &TrustStore,
    caps: &[String],
    req: RequestBody,
) -> SynapseMessage {
    match req {
        RequestBody::Ping => SynapseMessage::pong(DAEMON_SENDER),
        RequestBody::Health => SynapseMessage::data(DAEMON_SENDER, health_json()),
        RequestBody::Trust(op) => {
            let required = required_capability_for(&op);
            if !is_granted(caps, required) {
                return SynapseMessage::error(
                    DAEMON_SENDER,
                    error_code::CAPABILITY_DENIED,
                    format!("capability {required:?} not granted"),
                );
            }
            handle_trust(store, op)
        }
    }
}

fn health_json() -> serde_json::Value {
    json!({
        "status": "ok",
        "protocol_version": PROTOCOL_VERSION,
        "default_model": DEFAULT_MODEL,
        "subsystems": ["trust"],
    })
}

fn handle_trust(store: &TrustStore, op: TrustOp) -> SynapseMessage {
    match op {
        TrustOp::RecordOutcome {
            agent_id,
            decision_id,
            outcome,
            feedback_source,
            confidence,
            domain,
        } => {
            let parsed = match Outcome::parse(&outcome) {
                Ok(o) => o,
                Err(e) => return trust_err(e),
            };
            match store.reputation.record_outcome(
                &agent_id,
                &decision_id,
                parsed,
                &feedback_source,
                confidence,
                &domain,
            ) {
                Ok(()) => SynapseMessage::ok(DAEMON_SENDER),
                Err(e) => trust_err(e),
            }
        }
        TrustOp::GetScore { agent_id, domain } => {
            match store.reputation.get_reputation_score(&agent_id, &domain) {
                Ok(score) => SynapseMessage::data(
                    DAEMON_SENDER,
                    json!({ "agent_id": agent_id, "domain": domain, "score": score }),
                ),
                Err(e) => trust_err(e),
            }
        }
        TrustOp::ShouldTrust { agent_id, domain } => {
            match store.reputation.should_trust(&agent_id, &domain) {
                Ok((trust, reason)) => SynapseMessage::data(
                    DAEMON_SENDER,
                    json!({ "agent_id": agent_id, "domain": domain, "trusted": trust, "reason": reason }),
                ),
                Err(e) => trust_err(e),
            }
        }
        TrustOp::RankAgents { domain } => {
            match store.reputation.rank_agents(&domain) {
                Ok(ranked) => {
                    let agents: Vec<serde_json::Value> = ranked
                        .into_iter()
                        .map(|(id, score)| json!({ "agent_id": id, "score": score }))
                        .collect();
                    SynapseMessage::data(
                        DAEMON_SENDER,
                        json!({ "domain": domain, "agents": agents }),
                    )
                }
                Err(e) => trust_err(e),
            }
        }
    }
}

fn trust_err(e: TrustError) -> SynapseMessage {
    SynapseMessage::error(DAEMON_SENDER, error_code::TRUST_ERROR, e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::{Body, ResponseBody};

    fn store() -> TrustStore {
        TrustStore::new_in_memory().unwrap()
    }

    #[test]
    fn ping_yields_pong() {
        let s = store();
        let req = SynapseMessage::request("c", RequestBody::Ping).to_json().unwrap();
        let resp = dispatch(&s, &req);
        assert!(matches!(resp.body, Body::Response(ResponseBody::Pong)));
    }

    #[test]
    fn invalid_json_yields_bad_request() {
        let s = store();
        let resp = dispatch(&s, "{not json}");
        match resp.body {
            Body::Response(ResponseBody::Error { code, .. }) => {
                assert_eq!(code, error_code::BAD_REQUEST)
            }
            other => panic!("expected error, got {other:?}"),
        }
    }

    fn trust_caps() -> Vec<String> {
        vec!["trust.read".into(), "trust.write".into()]
    }

    #[test]
    fn record_outcome_then_get_score() {
        let s = store();
        let write = SynapseMessage::request_with_caps(
            "c",
            trust_caps(),
            RequestBody::Trust(TrustOp::RecordOutcome {
                agent_id: "sec".into(),
                decision_id: "d1".into(),
                outcome: "correct".into(),
                feedback_source: "human".into(),
                confidence: 1.0,
                domain: "security".into(),
            }),
        )
        .to_json()
        .unwrap();
        assert!(matches!(dispatch(&s, &write).body, Body::Response(ResponseBody::Ok)));

        let read = SynapseMessage::request_with_caps(
            "c",
            trust_caps(),
            RequestBody::Trust(TrustOp::GetScore {
                agent_id: "sec".into(),
                domain: "security".into(),
            }),
        )
        .to_json()
        .unwrap();
        match dispatch(&s, &read).body {
            Body::Response(ResponseBody::Data(v)) => {
                assert_eq!(v["score"], 100.0);
                assert_eq!(v["agent_id"], "sec");
            }
            other => panic!("expected data, got {other:?}"),
        }
    }

    #[test]
    fn should_trust_returns_decision() {
        let s = store();
        let req = SynapseMessage::request_with_caps(
            "c",
            trust_caps(),
            RequestBody::Trust(TrustOp::ShouldTrust {
                agent_id: "unknown".into(),
                domain: "any".into(),
            }),
        )
        .to_json()
        .unwrap();
        match dispatch(&s, &req).body {
            Body::Response(ResponseBody::Data(v)) => {
                assert_eq!(v["trusted"], false);
            }
            other => panic!("expected data, got {other:?}"),
        }
    }

    #[test]
    fn health_reports_subsystems() {
        let s = store();
        let req = SynapseMessage::request("c", RequestBody::Health).to_json().unwrap();
        match dispatch(&s, &req).body {
            Body::Response(ResponseBody::Data(v)) => {
                assert_eq!(v["default_model"], DEFAULT_MODEL);
                let subsystems = v["subsystems"].as_array().unwrap();
                assert!(subsystems.iter().any(|s| s == "trust"));
                // Daemon banner/health must only list subsystems that are
                // actually implemented in the Rust process today.
                assert!(!subsystems.iter().any(|s| s == "identity"));
                assert!(!subsystems.iter().any(|s| s == "vault"));
                assert!(!subsystems.iter().any(|s| s == "a2a"));
            }
            other => panic!("expected data, got {other:?}"),
        }
    }

    #[test]
    fn trust_op_without_capability_is_denied() {
        let s = store();
        let req = SynapseMessage::request(
            "c",
            RequestBody::Trust(TrustOp::GetScore {
                agent_id: "x".into(),
                domain: "any".into(),
            }),
        )
        .to_json()
        .unwrap();
        match dispatch(&s, &req).body {
            Body::Response(ResponseBody::Error { code, message }) => {
                assert_eq!(code, error_code::CAPABILITY_DENIED);
                assert!(message.contains("trust.read"));
            }
            other => panic!("expected capability_denied, got {other:?}"),
        }
    }

    #[test]
    fn trust_write_requires_trust_write_capability() {
        let s = store();
        // Caller has trust.read but not trust.write — record_outcome must fail.
        let req = SynapseMessage::request_with_caps(
            "c",
            vec!["trust.read".into()],
            RequestBody::Trust(TrustOp::RecordOutcome {
                agent_id: "x".into(),
                decision_id: "d".into(),
                outcome: "correct".into(),
                feedback_source: "human".into(),
                confidence: 1.0,
                domain: "any".into(),
            }),
        )
        .to_json()
        .unwrap();
        match dispatch(&s, &req).body {
            Body::Response(ResponseBody::Error { code, .. }) => {
                assert_eq!(code, error_code::CAPABILITY_DENIED);
            }
            other => panic!("expected capability_denied, got {other:?}"),
        }
    }

    #[test]
    fn wildcard_capability_grants_all_trust_ops() {
        let s = store();
        let req = SynapseMessage::request_with_caps(
            "c",
            vec!["*".into()],
            RequestBody::Trust(TrustOp::GetScore {
                agent_id: "x".into(),
                domain: "any".into(),
            }),
        )
        .to_json()
        .unwrap();
        assert!(matches!(
            dispatch(&s, &req).body,
            Body::Response(ResponseBody::Data(_))
        ));
    }

    #[test]
    fn ping_does_not_require_capability() {
        let s = store();
        let req = SynapseMessage::request("c", RequestBody::Ping).to_json().unwrap();
        assert!(matches!(
            dispatch(&s, &req).body,
            Body::Response(ResponseBody::Pong)
        ));
    }
}
