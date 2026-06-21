// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

//! End-to-end integration test for the **Unix-socket IPC server**: a real
//! client connects over a real socket and exchanges Synapse Protocol messages.

use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use synapse_daemon::ipc;
use synapse_daemon::trust::TrustStore;
use synapse_daemon::protocol::{
    Body, TrustOp, RequestBody, ResponseBody, SynapseMessage,
};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;

fn unique_socket(tag: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!("synapse-ipc-{tag}-{}-{nanos}.sock", std::process::id()))
}

async fn start_server(path: &PathBuf) {
    let _ = std::fs::remove_file(path);
    let store = Arc::new(TrustStore::new_in_memory().unwrap());
    let server_path = path.clone();
    tokio::spawn(async move {
        let _ = ipc::serve(&server_path, store).await;
    });
    for _ in 0..100 {
        if path.exists() {
            return;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    panic!("server socket never appeared at {}", path.display());
}

async fn exchange(stream: &mut UnixStream, request: &SynapseMessage) -> SynapseMessage {
    let (read_half, mut write_half) = stream.split();
    let mut reader = BufReader::new(read_half);
    let line = format!("{}\n", request.to_json().unwrap());
    write_half.write_all(line.as_bytes()).await.unwrap();
    write_half.flush().await.unwrap();
    let mut response = String::new();
    reader.read_line(&mut response).await.unwrap();
    SynapseMessage::from_json(response.trim()).unwrap()
}

#[tokio::test]
async fn ping_pong_over_real_socket() {
    let path = unique_socket("ping");
    start_server(&path).await;

    let mut stream = UnixStream::connect(&path).await.expect("connect");
    let resp = exchange(&mut stream, &SynapseMessage::request("client", RequestBody::Ping)).await;
    assert!(matches!(resp.body, Body::Response(ResponseBody::Pong)));

    let _ = std::fs::remove_file(&path);
}

#[tokio::test]
async fn trust_record_and_score_over_real_socket() {
    let path = unique_socket("trust");
    start_server(&path).await;

    let mut stream = UnixStream::connect(&path).await.expect("connect");

    let caps = vec!["trust.read".to_string(), "trust.write".to_string()];

    let record = SynapseMessage::request_with_caps(
        "client",
        caps.clone(),
        RequestBody::Trust(TrustOp::RecordOutcome {
            agent_id: "sentinel".into(),
            decision_id: "d1".into(),
            outcome: "correct".into(),
            feedback_source: "human".into(),
            confidence: 1.0,
            domain: "security".into(),
        }),
    );
    let record_resp = exchange(&mut stream, &record).await;
    assert!(matches!(record_resp.body, Body::Response(ResponseBody::Ok)));

    let score = SynapseMessage::request_with_caps(
        "client",
        caps,
        RequestBody::Trust(TrustOp::GetScore {
            agent_id: "sentinel".into(),
            domain: "security".into(),
        }),
    );
    let score_resp = exchange(&mut stream, &score).await;
    match score_resp.body {
        Body::Response(ResponseBody::Data(v)) => assert_eq!(v["score"], 100.0),
        other => panic!("expected data, got {other:?}"),
    }

    let _ = std::fs::remove_file(&path);
}
