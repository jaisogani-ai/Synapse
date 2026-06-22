# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""End-to-end encryption for A2A payloads.

mTLS protects the *transport* hop-by-hop. End-to-end encryption protects the
*payload* sender-to-recipient: even if the message passes through a relay,
a logging proxy, or a compromised transport, only the holder of the
recipient's private key can read it.

Scheme: a sealed-box / ECIES construction using only well-reviewed
primitives from `cryptography`:

  1. Sender generates an ephemeral X25519 keypair.
  2. ECDH(ephemeral_private, recipient_static_public) → shared secret.
  3. HKDF-SHA256(shared_secret, info=sender|recipient) → 32-byte AES key.
  4. AES-256-GCM encrypts the payload. The (sender, recipient) pair is bound
     into the GCM AAD so a ciphertext cannot be replayed claiming a
     different sender or redirected to a different recipient.
  5. The wire envelope carries: version, alg, ephemeral public key, nonce,
     ciphertext+tag, sender id, recipient id. **No private key material and
     no plaintext ever leave the sender.**

Forward secrecy: the ephemeral key is discarded after one message, so
compromising a recipient's long-term private key later does not decrypt
messages captured earlier (each used a unique ephemeral → unique shared
secret).

This is opt-in. The A2A path runs unencrypted-payload-over-(HTTP|mTLS) by
default; turn E2E on by generating keypairs, distributing public keys, and
passing the recipient's public key to ``seal`` / your own private key to
``unseal``.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

#: Envelope format version. Bump on any breaking change to the scheme.
E2E_VERSION = 1

#: Algorithm identifier carried in the envelope for agility / clarity.
E2E_ALG = "x25519-hkdf-sha256-aes256gcm"

#: AES-256-GCM nonce length.
_NONCE_BYTES = 12

#: Derived key length (AES-256).
_KEY_BYTES = 32

#: HKDF salt — a fixed, public, scheme-specific constant.
_HKDF_SALT = b"synapse-e2e-v1"


class E2EError(Exception):
    """Raised on any encryption / decryption / key-format failure."""


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


# ── key generation + storage ───────────────────────────────────────────────


@dataclass(frozen=True)
class KeyPairFiles:
    """Paths to a generated X25519 keypair on disk."""

    agent_id: str
    private_path: Path
    public_path: Path


def generate_keypair(agent_id: str, out_dir: Path) -> KeyPairFiles:
    """Generate an X25519 keypair for ``agent_id``.

    Writes ``<out_dir>/<agent_id>.x25519`` (private, PEM, ``chmod 600``) and
    ``<out_dir>/<agent_id>.x25519.pub`` (public, PEM). The public file is the
    one you distribute to peers; the private file never leaves this host.
    """
    if not agent_id:
        raise E2EError("agent_id is required")
    out_dir.mkdir(parents=True, exist_ok=True)

    private = X25519PrivateKey.generate()
    public = private.public_key()

    private_path = out_dir / f"{agent_id}.x25519"
    public_path = out_dir / f"{agent_id}.x25519.pub"

    private_path.write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    try:
        import os

        os.chmod(private_path, 0o600)
    except OSError:
        pass

    return KeyPairFiles(
        agent_id=agent_id, private_path=private_path, public_path=public_path
    )


def load_private_key(path: Path) -> X25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (ValueError, OSError) as exc:
        raise E2EError(f"cannot load private key {path}: {exc}") from exc
    if not isinstance(key, X25519PrivateKey):
        raise E2EError(f"{path} is not an X25519 private key")
    return key


def load_public_key(path: Path) -> X25519PublicKey:
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except (ValueError, OSError) as exc:
        raise E2EError(f"cannot load public key {path}: {exc}") from exc
    if not isinstance(key, X25519PublicKey):
        raise E2EError(f"{path} is not an X25519 public key")
    return key


# ── seal / unseal ───────────────────────────────────────────────────────────


def _derive_key(shared_secret: bytes, sender_id: str, recipient_id: str) -> bytes:
    """HKDF-SHA256 the ECDH shared secret into an AES-256 key, bound to the pair."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_BYTES,
        salt=_HKDF_SALT,
        info=f"{sender_id}->{recipient_id}".encode("utf-8"),
    )
    return hkdf.derive(shared_secret)


def _aad(sender_id: str, recipient_id: str) -> bytes:
    """Additional authenticated data: binds the ciphertext to the agent pair."""
    return f"synapse-e2e|{sender_id}|{recipient_id}".encode("utf-8")


def seal(
    plaintext: bytes,
    recipient_public_key: X25519PublicKey,
    sender_id: str,
    recipient_id: str,
) -> dict[str, object]:
    """Encrypt ``plaintext`` for the recipient. Returns a JSON-able envelope.

    The envelope is safe to transmit over any channel — only the holder of
    ``recipient``'s X25519 private key can decrypt it.
    """
    ephemeral_private = X25519PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key()
    shared = ephemeral_private.exchange(recipient_public_key)
    key = _derive_key(shared, sender_id, recipient_id)

    import os

    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(
        nonce, plaintext, _aad(sender_id, recipient_id)
    )

    epk_raw = ephemeral_public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "v": E2E_VERSION,
        "alg": E2E_ALG,
        "sender": sender_id,
        "recipient": recipient_id,
        "epk": _b64e(epk_raw),
        "nonce": _b64e(nonce),
        "ct": _b64e(ciphertext),
    }


def unseal(
    envelope: dict[str, object],
    recipient_private_key: X25519PrivateKey,
) -> bytes:
    """Decrypt a :func:`seal` envelope. Returns the plaintext.

    Raises :class:`E2EError` on any format error, wrong key, tampering, or a
    sender/recipient mismatch (the pair is bound into the AAD).
    """
    if not isinstance(envelope, dict):
        raise E2EError("envelope must be a JSON object")
    if envelope.get("v") != E2E_VERSION:
        raise E2EError(f"unsupported envelope version: {envelope.get('v')}")
    if envelope.get("alg") != E2E_ALG:
        raise E2EError(f"unsupported algorithm: {envelope.get('alg')}")

    sender_id = str(envelope.get("sender", ""))
    recipient_id = str(envelope.get("recipient", ""))
    try:
        epk_raw = _b64d(str(envelope["epk"]))
        nonce = _b64d(str(envelope["nonce"]))
        ciphertext = _b64d(str(envelope["ct"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise E2EError(f"malformed envelope: {exc}") from exc

    try:
        ephemeral_public = X25519PublicKey.from_public_bytes(epk_raw)
        shared = recipient_private_key.exchange(ephemeral_public)
    except ValueError as exc:
        raise E2EError(f"bad ephemeral public key: {exc}") from exc

    key = _derive_key(shared, sender_id, recipient_id)
    try:
        return AESGCM(key).decrypt(
            nonce, ciphertext, _aad(sender_id, recipient_id)
        )
    except Exception as exc:  # cryptography raises InvalidTag on tamper/wrong key
        raise E2EError(
            "decryption failed — wrong key, tampered ciphertext, or "
            "sender/recipient mismatch"
        ) from exc


def is_encrypted_envelope(obj: object) -> bool:
    """Whether ``obj`` looks like a Synapse E2E envelope."""
    return (
        isinstance(obj, dict)
        and obj.get("alg") == E2E_ALG
        and "epk" in obj
        and "ct" in obj
    )


# ── public-key registry (agent_id -> public key path) ──────────────────────


class PublicKeyRegistry:
    """Resolve ``agent_id`` to its X25519 public key from a directory.

    Public keys live as ``<dir>/<agent_id>.x25519.pub``. Distributing a
    peer's public key = dropping their ``.pub`` file into this directory.
    """

    def __init__(self, key_dir: Path) -> None:
        self._dir = key_dir

    def path_for(self, agent_id: str) -> Path:
        return self._dir / f"{agent_id}.x25519.pub"

    def has(self, agent_id: str) -> bool:
        return self.path_for(agent_id).exists()

    def get(self, agent_id: str) -> X25519PublicKey:
        path = self.path_for(agent_id)
        if not path.exists():
            raise E2EError(f"no public key for agent {agent_id!r} in {self._dir}")
        return load_public_key(path)

    def list_agents(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(
            p.name[: -len(".x25519.pub")]
            for p in self._dir.glob("*.x25519.pub")
        )
