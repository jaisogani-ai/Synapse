# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Chunked, resumable file transfer over plain HTTP.

For attachments larger than :data:`INLINE_THRESHOLD_BYTES` the sender stops
embedding base64 bytes in the A2A ``FilePart``. Instead it:

  1. Stores the file in a content-addressed local cache keyed by SHA-256.
  2. Builds a ``FilePart`` with ``uri = synapse+blob://<sender>/<sha256>``
     (the A2A spec already permits ``uri`` as a ``FilePart`` alternative
     to inline ``bytes`` — we do not invent a new field).
  3. Resolves that URI to an HTTP URL the receiver can fetch with standard
     HTTP ``Range`` requests for resumable streaming.

The receiver-side helper :func:`fetch_blob` streams chunks, supports
``Range: bytes=<offset>-`` resumption, and verifies SHA-256 integrity
end-to-end so a tampered or truncated blob is rejected.

There is no new protocol here — this is pure A2A + HTTP/1.1.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

#: Files at or below this size stay inline in the FilePart's base64 bytes.
INLINE_THRESHOLD_BYTES = 256 * 1024  # 256 KiB

#: Hard ceiling on a single chunked transfer.
MAX_BLOB_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB

#: Default chunk size for streamed reads/writes.
CHUNK_BYTES = 64 * 1024  # 64 KiB

#: URI scheme used inside FilePart.uri for blobs hosted by Synapse senders.
URI_SCHEME = "synapse+blob"


@dataclass(frozen=True)
class BlobRef:
    """A content-addressed reference to a sender-hosted blob."""

    sha256_hex: str
    size: int
    name: str
    mime_type: str
    uri: str


def sha256_file(path: Path) -> tuple[str, int]:
    """Return ``(sha256_hex, size_bytes)`` for ``path``."""
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_BYTES)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


class BlobCache:
    """Content-addressed local cache. Files are stored by SHA-256 hex."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def path_for(self, sha256_hex: str) -> Path:
        # Two-level fan-out keeps directory entries manageable.
        return self._root / sha256_hex[:2] / sha256_hex

    def has(self, sha256_hex: str) -> bool:
        return self.path_for(sha256_hex).exists()

    def put(self, source: Path) -> tuple[str, int]:
        """Copy ``source`` into the cache. Returns ``(sha256_hex, size)``."""
        sha, size = sha256_file(source)
        if size > MAX_BLOB_BYTES:
            raise ValueError(
                f"blob too large: {size} bytes (max {MAX_BLOB_BYTES})"
            )
        dest = self.path_for(sha)
        if dest.exists():
            return sha, size
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        shutil.copyfile(source, tmp)
        os.replace(tmp, dest)
        return sha, size

    def open_read(self, sha256_hex: str):  # type: ignore[no-untyped-def]
        return self.path_for(sha256_hex).open("rb")

    def size(self, sha256_hex: str) -> int:
        return self.path_for(sha256_hex).stat().st_size


def make_blob_uri(sender_id: str, sha256_hex: str) -> str:
    """``synapse+blob://<sender_id>/<sha256_hex>`` — A2A-spec ``uri`` value."""
    return f"{URI_SCHEME}://{sender_id}/{sha256_hex}"


def parse_blob_uri(uri: str) -> tuple[str, str] | None:
    """Return ``(sender_id, sha256_hex)`` or ``None`` if ``uri`` is not ours."""
    if not uri.startswith(f"{URI_SCHEME}://"):
        return None
    rest = uri[len(f"{URI_SCHEME}://"):]
    if "/" not in rest:
        return None
    sender_id, sha = rest.split("/", 1)
    if not sender_id or len(sha) != 64:
        return None
    return sender_id, sha


def fetch_blob(
    http_url: str,
    expected_sha256: str,
    expected_size: int,
    dest: Path,
    *,
    chunk_bytes: int = CHUNK_BYTES,
    progress: "callable | None" = None,
    resume: bool = True,
) -> int:
    """Download a blob to ``dest`` with resume + SHA-256 verification.

    Returns the total number of bytes written. Raises ``ValueError`` if the
    integrity check fails. Existing partial files are extended with a
    ``Range`` request when ``resume=True``.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and resume:
        offset = dest.stat().st_size
        if offset >= expected_size:
            offset = 0
            dest.unlink(missing_ok=True)
    else:
        offset = 0
        if dest.exists():
            dest.unlink()

    headers = {"Accept": "application/octet-stream"}
    if offset > 0:
        headers["Range"] = f"bytes={offset}-"
    req = urllib.request.Request(http_url, headers=headers)

    h = hashlib.sha256()
    # Re-hash any bytes already on disk so the final digest covers everything.
    if offset > 0:
        with dest.open("rb") as existing:
            while True:
                chunk = existing.read(chunk_bytes)
                if not chunk:
                    break
                h.update(chunk)

    written = offset
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        # If server ignored Range and returned 200, restart from 0.
        if resp.status == 200 and offset > 0:
            offset = 0
            written = 0
            h = hashlib.sha256()
            dest.unlink(missing_ok=True)
        with dest.open("ab" if offset > 0 else "wb") as out:
            while True:
                chunk = resp.read(chunk_bytes)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                written += len(chunk)
                if progress is not None:
                    progress(written, expected_size)

    if written != expected_size:
        raise ValueError(
            f"size mismatch: got {written}, expected {expected_size}"
        )
    if h.hexdigest() != expected_sha256:
        dest.unlink(missing_ok=True)
        raise ValueError("sha256 mismatch — blob tampered or corrupted")
    return written


def serve_blob(
    cache: BlobCache,
    sha256_hex: str,
    range_header: str | None,
    write_status: "callable",
    write_header: "callable",
    end_headers: "callable",
    write_body: "callable",
) -> None:
    """Serve a blob over HTTP with ``Range`` support.

    The five callables let this function plug into either ``http.server`` or
    a test harness without binding to a real socket.
    """
    if not cache.has(sha256_hex):
        write_status(404)
        write_header("Content-Type", "text/plain")
        end_headers()
        write_body(b"blob not found")
        return

    size = cache.size(sha256_hex)
    start, end = 0, size - 1
    if range_header and range_header.startswith("bytes="):
        spec = range_header[len("bytes="):]
        if "-" in spec:
            s, e = spec.split("-", 1)
            if s:
                start = int(s)
            if e:
                end = int(e)
            if start < 0 or start >= size or end >= size or end < start:
                write_status(416)
                write_header("Content-Range", f"bytes */{size}")
                end_headers()
                return

    length = end - start + 1
    if range_header and (start, end) != (0, size - 1):
        write_status(206)
        write_header("Content-Range", f"bytes {start}-{end}/{size}")
    else:
        write_status(200)
    write_header("Accept-Ranges", "bytes")
    write_header("Content-Type", "application/octet-stream")
    write_header("Content-Length", str(length))
    write_header("X-Synapse-Sha256", sha256_hex)
    end_headers()

    with cache.open_read(sha256_hex) as src:
        src.seek(start)
        remaining = length
        while remaining > 0:
            chunk = src.read(min(CHUNK_BYTES, remaining))
            if not chunk:
                break
            write_body(chunk)
            remaining -= len(chunk)
