# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""A2A transport — JSON-RPC over HTTP (per A2A spec).

Uses Python stdlib only (urllib + http.server). The transport carries:
- the JSON-RPC payload
- the sender's id (X-A2A-Sender header)
- the HMAC signature (X-A2A-Signature header)

The receiving side verifies both before any task is touched.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

HEADER_SENDER = "X-A2A-Sender"
HEADER_SIGNATURE = "X-A2A-Signature"
HEADER_TIMESTAMP = "X-A2A-Timestamp"
#: Signed JWT carrying the sender's capability set. Verified by the receiver
#: against a method->capability table; missing token → request denied.
HEADER_TOKEN = "X-A2A-Token"
DEFAULT_TIMEOUT = 2.0
#: Hard cap on inbound POST body (~12 MiB). Larger artifacts use the blob
#: endpoint with chunked transfer instead of inline base64.
MAX_REQUEST_BYTES = 12 * 1024 * 1024


@dataclass(frozen=True)
class TransportError(Exception):
    """Raised on unreachable target or transport failure."""

    message: str

    def __str__(self) -> str:
        return self.message


class TransportUnreachable(Exception):
    """The target daemon is not reachable."""


def post_jsonrpc(
    url: str,
    payload_bytes: bytes,
    sender_id: str,
    signature_hex: str,
    timeout: float = DEFAULT_TIMEOUT,
    timestamp: int | None = None,
    token: str = "",
) -> dict[str, Any]:
    """POST a JSON-RPC payload with sender + signature + timestamp + token headers.

    The timestamp is part of the signed material — see ``a2a_signer.py``.
    The ``token`` carries the sender's capability set; the receiver
    rejects the request if the token's caps don't authorise the RPC method.
    Raises TransportUnreachable on connection refused / timeout / DNS errors.
    """
    import time as _time
    ts = int(timestamp if timestamp is not None else _time.time())
    headers = {
        "Content-Type": "application/json",
        HEADER_SENDER: sender_id,
        HEADER_SIGNATURE: signature_hex,
        HEADER_TIMESTAMP: str(ts),
    }
    if token:
        headers[HEADER_TOKEN] = token
    req = urllib.request.Request(
        url,
        data=payload_bytes,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
        raise TransportUnreachable(f"target unreachable: {exc}") from exc


def is_reachable(url: str, timeout: float = 1.0) -> bool:
    """Quick presence check — does the target accept TCP connections?"""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 500
    except urllib.error.HTTPError as e:
        return 200 <= e.code < 500
    except Exception:
        return False


# ─── Embedded HTTP receiver ────────────────────────────────────────────────


HandlerFn = Callable[..., dict[str, Any]]


class A2AServer:
    """HTTP JSON-RPC receiver with blob + presence endpoints.

    The server exposes:

    * ``POST /a2a``          A2A JSON-RPC envelope (signed, MAC-verified).
    * ``GET  /blob/<sha>``   Chunked, range-aware blob download (large files).
    * ``GET  /presence``     ``{"status": "online|busy|offline"}`` snapshot.
    * ``GET  /``             Liveness probe (``synapse-a2a-receiver``).
    """

    def __init__(
        self,
        port: int,
        handler: HandlerFn,
        *,
        blob_cache: "object | None" = None,
        presence_fn: "callable | None" = None,
    ) -> None:
        self._port = port
        self._handler = handler
        self._blob_cache = blob_cache
        self._presence_fn = presence_fn
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}/a2a"

    def blob_url(self, sha256_hex: str) -> str:
        return f"http://127.0.0.1:{self._port}/blob/{sha256_hex}"

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:  # silence stdout
                return

            def do_GET(self) -> None:
                if self.path.startswith("/blob/") and outer._blob_cache is not None:
                    from .blob import serve_blob  # local import to avoid cycle
                    sha = self.path[len("/blob/"):]
                    serve_blob(
                        outer._blob_cache,
                        sha,
                        self.headers.get("Range"),
                        write_status=lambda s: self.send_response(s),
                        write_header=lambda k, v: self.send_header(k, v),
                        end_headers=lambda: self.end_headers(),
                        write_body=lambda b: self.wfile.write(b),
                    )
                    return
                if self.path == "/presence":
                    status = (
                        outer._presence_fn() if outer._presence_fn else "online"
                    )
                    body = json.dumps({"status": status}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"synapse-a2a-receiver")

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_REQUEST_BYTES:
                    err = json.dumps({
                        "jsonrpc": "2.0",
                        "error": {"code": -32000, "message": f"payload too large ({length} bytes; max {MAX_REQUEST_BYTES})"},
                        "id": None,
                    }).encode()
                    self.send_response(413)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(err)))
                    self.end_headers()
                    self.wfile.write(err)
                    return
                body = self.rfile.read(length)
                sender = self.headers.get(HEADER_SENDER, "")
                signature = self.headers.get(HEADER_SIGNATURE, "")
                timestamp = self.headers.get(HEADER_TIMESTAMP, "")
                token = self.headers.get(HEADER_TOKEN, "")
                try:
                    result = outer._handler(body, sender, signature, timestamp, token)
                    payload = json.dumps(result).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except Exception:  # noqa: BLE001
                    # Never leak internal exception text on the wire.
                    err = json.dumps(
                        {"jsonrpc": "2.0", "error": {"code": -32000, "message": "internal error"}, "id": None}
                    ).encode()
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(err)))
                    self.end_headers()
                    self.wfile.write(err)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", self._port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
