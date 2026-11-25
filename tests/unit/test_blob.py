# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Chunked, resumable blob transfer: 1 MiB, HTTP Range resume, SHA-256.

The fetch tests run against a real loopback ``http.server`` that serves blobs
through :func:`synapse_cli.blob.serve_blob`.
"""

from __future__ import annotations

import hashlib
import random
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from synapse_cli.blob import (
    INLINE_THRESHOLD_BYTES,
    BlobCache,
    fetch_blob,
    make_blob_uri,
    parse_blob_uri,
    serve_blob,
    sha256_file,
)

ONE_MIB = 1024 * 1024


def _make_payload() -> bytes:
    return random.Random(1234).randbytes(ONE_MIB)


@pytest.fixture()
def blob(tmp_path: Path):
    data = _make_payload()
    src = tmp_path / "payload.bin"
    src.write_bytes(data)
    cache = BlobCache(tmp_path / "cache")
    sha, size = cache.put(src)
    return {"data": data, "sha": sha, "size": size, "cache": cache, "src": src}


@pytest.fixture()
def server(blob):
    cache: BlobCache = blob["cache"]
    seen_ranges: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            sha = self.path.rsplit("/", 1)[-1]
            rng = self.headers.get("Range")
            seen_ranges.append(rng)
            serve_blob(
                cache,
                sha,
                rng,
                self.send_response,
                self.send_header,
                self.end_headers,
                self.wfile.write,
            )

        def log_message(self, *args) -> None:  # silence test output
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "url": f"http://127.0.0.1:{httpd.server_address[1]}/blob/{blob['sha']}",
            "seen_ranges": seen_ranges,
        }
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_one_mib_blob_is_content_addressed(blob) -> None:
    assert blob["size"] == ONE_MIB
    assert ONE_MIB > INLINE_THRESHOLD_BYTES  # must take the blob path, not inline
    assert blob["sha"] == hashlib.sha256(blob["data"]).hexdigest()
    assert sha256_file(blob["src"]) == (blob["sha"], ONE_MIB)

    cache: BlobCache = blob["cache"]
    assert cache.has(blob["sha"])
    assert cache.size(blob["sha"]) == ONE_MIB
    # Putting the same bytes again is a no-op that returns the same address.
    assert cache.put(blob["src"]) == (blob["sha"], ONE_MIB)

    uri = make_blob_uri("alice", blob["sha"])
    assert uri == f"synapse+blob://alice/{blob['sha']}"
    assert parse_blob_uri(uri) == ("alice", blob["sha"])
    assert parse_blob_uri("https://example.com/x") is None
    assert parse_blob_uri("synapse+blob://alice/short") is None


def test_fetch_full_blob_verifies_sha256(blob, server, tmp_path: Path) -> None:
    dest = tmp_path / "out" / "full.bin"
    written = fetch_blob(server["url"], blob["sha"], blob["size"], dest)
    assert written == ONE_MIB
    assert dest.read_bytes() == blob["data"]
    assert server["seen_ranges"] == [None]


def test_fetch_resumes_partial_download_with_range(blob, server, tmp_path: Path) -> None:
    dest = tmp_path / "out" / "resume.bin"
    dest.parent.mkdir(parents=True)
    offset = 300_000
    dest.write_bytes(blob["data"][:offset])  # simulate an interrupted download

    progress: list[tuple[int, int]] = []
    written = fetch_blob(
        server["url"],
        blob["sha"],
        blob["size"],
        dest,
        progress=lambda done, total: progress.append((done, total)),
    )

    assert written == ONE_MIB
    assert dest.read_bytes() == blob["data"]
    assert server["seen_ranges"] == [f"bytes={offset}-"]
    assert progress and progress[0][0] > offset  # picked up where it left off
    assert progress[-1] == (ONE_MIB, ONE_MIB)


def test_fetch_rejects_tampered_sha256_and_removes_file(blob, server, tmp_path: Path) -> None:
    dest = tmp_path / "out" / "tampered.bin"
    wrong_sha = "0" * 64
    with pytest.raises(ValueError, match="sha256 mismatch"):
        fetch_blob(server["url"], wrong_sha, blob["size"], dest)
    assert not dest.exists()


def test_fetch_rejects_size_mismatch(blob, server, tmp_path: Path) -> None:
    dest = tmp_path / "out" / "short.bin"
    with pytest.raises(ValueError, match="size mismatch"):
        fetch_blob(server["url"], blob["sha"], blob["size"] + 1, dest)


def _serve(cache: BlobCache, sha: str, range_header: str | None):
    status: list[int] = []
    headers: dict[str, str] = {}
    body = bytearray()
    serve_blob(
        cache,
        sha,
        range_header,
        status.append,
        lambda k, v: headers.__setitem__(k, v),
        lambda: None,
        body.extend,
    )
    return status[0], headers, bytes(body)


def test_serve_blob_range_and_error_statuses(blob) -> None:
    cache, sha, data = blob["cache"], blob["sha"], blob["data"]

    status, headers, body = _serve(cache, sha, None)
    assert status == 200 and body == data
    assert headers["Accept-Ranges"] == "bytes"
    assert headers["X-Synapse-Sha256"] == sha

    status, headers, body = _serve(cache, sha, "bytes=1000-1999")
    assert status == 206 and body == data[1000:2000]
    assert headers["Content-Range"] == f"bytes 1000-1999/{ONE_MIB}"
    assert headers["Content-Length"] == "1000"

    status, headers, _ = _serve(cache, sha, f"bytes={ONE_MIB}-")
    assert status == 416
    assert headers["Content-Range"] == f"bytes */{ONE_MIB}"

    status, _, body = _serve(cache, "f" * 64, None)
    assert status == 404 and body == b"blob not found"
