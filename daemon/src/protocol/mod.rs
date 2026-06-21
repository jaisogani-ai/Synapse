// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

//! # Synapse Protocol v1.0
//!
//! The line-delimited JSON message format spoken between the daemon and every
//! satellite (adapters, MCP servers, clients) over a local Unix socket.
//!
//! Every message is a [`SynapseMessage`] envelope carrying an id, the protocol
//! [`PROTOCOL_VERSION`], a timestamp, the sender, and a [`Body`] — a tagged
//! union of [`RequestBody`], [`ResponseBody`], and [`EventBody`].
//!
//! Enums use serde's default external tagging, so the wire form is compact and
//! unambiguous, e.g.:
//!
//! ```json
//! { "id": "…", "version": "1.0", "timestamp": "…", "sender": "agent-1",
//!   "body": { "request": { "trust": { "record_outcome": {
//!       "agent_id": "sec", "decision_id": "d1", "outcome": "correct",
//!       "feedback_source": "human", "confidence": 1.0, "domain": "security" } } } } }
//! ```

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// The protocol version this daemon speaks.
pub const PROTOCOL_VERSION: &str = "1.0";

/// The default model for all Synapse agent reasoning.
pub const DEFAULT_MODEL: &str = "claude-opus-4-8";

/// An operation against the trust subsystem (reputation store).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TrustOp {
    /// Record an outcome for an agent/decision.
    RecordOutcome {
        agent_id: String,
        decision_id: String,
        outcome: String,
        feedback_source: String,
        confidence: f64,
        domain: String,
    },
    /// Query the reputation score for an agent in a domain.
    GetScore {
        agent_id: String,
        domain: String,
    },
    /// Ask whether an agent should be trusted in a domain.
    ShouldTrust {
        agent_id: String,
        domain: String,
    },
    /// Rank all agents in a domain by reputation (best first).
    RankAgents {
        domain: String,
    },
}

/// A request from a satellite to the daemon.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RequestBody {
    /// Liveness probe.
    Ping,
    /// Daemon health.
    Health,
    /// A trust/reputation operation.
    Trust(TrustOp),
}

/// A reply from the daemon to a satellite.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ResponseBody {
    /// Reply to [`RequestBody::Ping`].
    Pong,
    /// Operation succeeded with no payload.
    Ok,
    /// Operation succeeded with a JSON payload.
    Data(serde_json::Value),
    /// Operation failed.
    Error {
        /// Machine-readable error code.
        code: String,
        /// Human-readable message.
        message: String,
    },
}

/// An unsolicited event emitted by the daemon.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EventBody {
    /// A human-readable notice (audit/log surface).
    Notice(String),
}

/// The tagged union of message bodies.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Body {
    /// A request.
    Request(RequestBody),
    /// A response.
    Response(ResponseBody),
    /// An event.
    Event(EventBody),
}

/// A Synapse Protocol message envelope.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SynapseMessage {
    /// Unique message id (UUID v4).
    pub id: String,
    /// Protocol version (see [`PROTOCOL_VERSION`]).
    pub version: String,
    /// Creation time (UTC).
    pub timestamp: DateTime<Utc>,
    /// Sender identity (agent id, MCP name, or client id).
    pub sender: String,
    /// The message body.
    pub body: Body,
}

impl SynapseMessage {
    /// Build a message with a fresh id, current version, and timestamp.
    pub fn new(sender: impl Into<String>, body: Body) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            version: PROTOCOL_VERSION.to_string(),
            timestamp: Utc::now(),
            sender: sender.into(),
            body,
        }
    }

    /// Convenience constructor for a request message.
    pub fn request(sender: impl Into<String>, request: RequestBody) -> Self {
        Self::new(sender, Body::Request(request))
    }

    /// Convenience constructor for a response message.
    pub fn response(sender: impl Into<String>, response: ResponseBody) -> Self {
        Self::new(sender, Body::Response(response))
    }

    /// A `pong` response.
    pub fn pong(sender: impl Into<String>) -> Self {
        Self::response(sender, ResponseBody::Pong)
    }

    /// An `ok` response.
    pub fn ok(sender: impl Into<String>) -> Self {
        Self::response(sender, ResponseBody::Ok)
    }

    /// A `data` response carrying a JSON payload.
    pub fn data(sender: impl Into<String>, value: serde_json::Value) -> Self {
        Self::response(sender, ResponseBody::Data(value))
    }

    /// An `error` response.
    pub fn error(
        sender: impl Into<String>,
        code: impl Into<String>,
        message: impl Into<String>,
    ) -> Self {
        Self::response(
            sender,
            ResponseBody::Error {
                code: code.into(),
                message: message.into(),
            },
        )
    }

    /// Serialize to a compact JSON string.
    pub fn to_json(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string(self)
    }

    /// Deserialize from a JSON string.
    pub fn from_json(s: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(s)
    }

    /// Whether this message uses a protocol version this daemon understands.
    pub fn is_supported_version(&self) -> bool {
        self.version == PROTOCOL_VERSION
    }
}

/// Well-known error codes used in [`ResponseBody::Error`].
pub mod error_code {
    /// The request could not be parsed.
    pub const BAD_REQUEST: &str = "bad_request";
    /// The protocol version is unsupported.
    pub const UNSUPPORTED_VERSION: &str = "unsupported_version";
    /// A trust operation failed.
    pub const TRUST_ERROR: &str = "trust_error";
    /// The requested operation is not implemented in this phase.
    pub const NOT_IMPLEMENTED: &str = "not_implemented";
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_model_is_opus() {
        assert_eq!(DEFAULT_MODEL, "claude-opus-4-8");
        assert_eq!(PROTOCOL_VERSION, "1.0");
    }

    #[test]
    fn ping_round_trips() {
        let msg = SynapseMessage::request("agent-1", RequestBody::Ping);
        let json = msg.to_json().unwrap();
        let back = SynapseMessage::from_json(&json).unwrap();
        assert_eq!(msg, back);
        assert!(back.is_supported_version());
    }

    #[test]
    fn trust_record_outcome_round_trips() {
        let msg = SynapseMessage::request(
            "agent-1",
            RequestBody::Trust(TrustOp::RecordOutcome {
                agent_id: "sec".into(),
                decision_id: "d1".into(),
                outcome: "correct".into(),
                feedback_source: "human".into(),
                confidence: 1.0,
                domain: "security".into(),
            }),
        );
        let json = msg.to_json().unwrap();
        assert!(json.contains("\"trust\""));
        assert!(json.contains("\"record_outcome\""));
        let back = SynapseMessage::from_json(&json).unwrap();
        assert_eq!(msg, back);
    }

    #[test]
    fn error_response_serializes_code_and_message() {
        let msg = SynapseMessage::error("daemon", error_code::BAD_REQUEST, "nope");
        let json = msg.to_json().unwrap();
        assert!(json.contains("bad_request"));
        let back = SynapseMessage::from_json(&json).unwrap();
        assert_eq!(msg, back);
    }

    #[test]
    fn trust_get_score_round_trips() {
        let msg = SynapseMessage::request(
            "client",
            RequestBody::Trust(TrustOp::GetScore {
                agent_id: "sentinel".into(),
                domain: "security".into(),
            }),
        );
        let json = msg.to_json().unwrap();
        let back = SynapseMessage::from_json(&json).unwrap();
        assert_eq!(msg, back);
    }
}
