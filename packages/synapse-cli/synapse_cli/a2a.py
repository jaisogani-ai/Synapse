# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""A2A protocol primitives — Task, Message, Part, Artifact (per a2aproject.org spec).

This module models the standard A2A objects and JSON-RPC envelope. No custom
fields are invented — only the spec's own structures (id, status, input,
artifacts, parts).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class PartKind(str, Enum):
    TEXT = "text"
    FILE = "file"
    DATA = "data"


class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class TextPart:
    kind: str = PartKind.TEXT.value
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "text": self.text}


@dataclass(frozen=True)
class FilePart:
    kind: str = PartKind.FILE.value
    name: str = ""
    mime_type: str = "application/octet-stream"
    bytes: str = ""  # base64-encoded content per A2A spec

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "file": {
                "name": self.name,
                "mimeType": self.mime_type,
                "bytes": self.bytes,
            },
        }


@dataclass(frozen=True)
class DataPart:
    kind: str = PartKind.DATA.value
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "data": self.data}


Part = TextPart | FilePart | DataPart


@dataclass(frozen=True)
class Message:
    role: str  # "user" | "agent"
    parts: tuple[Part, ...]
    message_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "parts": [p.to_dict() for p in self.parts],
            "messageId": self.message_id or str(uuid.uuid4()),
        }


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    name: str
    parts: tuple[Part, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "name": self.name,
            "parts": [p.to_dict() for p in self.parts],
        }


@dataclass(frozen=True)
class TaskStatus:
    state: str
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "timestamp": self.timestamp}


@dataclass(frozen=True)
class Task:
    """A2A Task object — strictly per spec.

    Fields: id, status, history, artifacts. No custom invented fields.
    """

    id: str
    context_id: str
    status: TaskStatus
    history: tuple[Message, ...] = ()
    artifacts: tuple[Artifact, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "contextId": self.context_id,
            "status": self.status.to_dict(),
            "history": [m.to_dict() for m in self.history],
            "artifacts": [a.to_dict() for a in self.artifacts],
            "kind": "task",
        }


# ─── JSON-RPC 2.0 envelope (per A2A transport spec) ─────────────────────────


@dataclass(frozen=True)
class JsonRpcRequest:
    method: str
    params: dict[str, Any]
    id: str = ""
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "params": self.params,
            "id": self.id or str(uuid.uuid4()),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class JsonRpcResponse:
    id: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            out["error"] = self.error
        else:
            out["result"] = self.result or {}
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)


# ─── Standard A2A methods ───────────────────────────────────────────────────

METHOD_MESSAGE_SEND = "message/send"
METHOD_TASKS_GET = "tasks/get"
METHOD_TASKS_RESULT = "tasks/result"


def new_task_id() -> str:
    return str(uuid.uuid4())


def new_context_id() -> str:
    return str(uuid.uuid4())
