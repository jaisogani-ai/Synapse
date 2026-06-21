// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

//! Integration tests for the **Synapse Protocol v1.0** wire format.

use synapse_daemon::protocol::{
    Body, TrustOp, RequestBody, ResponseBody, SynapseMessage, DEFAULT_MODEL,
    PROTOCOL_VERSION,
};

#[test]
fn every_message_round_trips_through_json() {
    let messages = vec![
        SynapseMessage::request("a", RequestBody::Ping),
        SynapseMessage::request("a", RequestBody::Health),
        SynapseMessage::request(
            "a",
            RequestBody::Trust(TrustOp::GetScore {
                agent_id: "sentinel".into(),
                domain: "security".into(),
            }),
        ),
        SynapseMessage::pong("daemon"),
        SynapseMessage::ok("daemon"),
        SynapseMessage::error("daemon", "trust_error", "boom"),
    ];
    for msg in messages {
        let json = msg.to_json().unwrap();
        let back = SynapseMessage::from_json(&json).unwrap();
        assert_eq!(msg, back);
        assert_eq!(back.version, PROTOCOL_VERSION);
    }
}

#[test]
fn unsupported_version_is_detectable() {
    let mut msg = SynapseMessage::pong("daemon");
    msg.version = "9.9".into();
    assert!(!msg.is_supported_version());
}

#[test]
fn default_model_is_claude_opus_4_8() {
    assert_eq!(DEFAULT_MODEL, "claude-opus-4-8");
}

#[test]
fn wire_form_is_compact_and_tagged() {
    let msg = SynapseMessage::request("agent-1", RequestBody::Ping);
    let json = msg.to_json().unwrap();
    assert!(json.contains("\"request\""));
    assert!(json.contains("\"ping\""));
    if let Body::Response(ResponseBody::Pong) = SynapseMessage::pong("d").body {
        // ok
    } else {
        panic!("pong is not a response");
    }
}
