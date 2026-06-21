# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Opt-in mutual TLS for A2A.

Synapse's HMAC-signed envelopes already give us authentication and
integrity. mTLS adds a second authentication layer **and** confidentiality
at the transport, so a network observer can't see the JSON-RPC payload
(useful when running across the public internet without a tunnel).

This module is intentionally minimal:

* No CA infrastructure. Each agent issues its own self-signed Ed25519 cert
  via :func:`generate_self_signed_cert`. The cert's CN is the agent_id.
* No revocation lists. To revoke, delete the cert from the receiver's
  trust directory and the next handshake from that peer fails.
* No rotation policy. Operators re-run ``synapse identity gen-cert`` and
  copy the new cert. Standard certs are valid for 365 days by default.

mTLS is **opt-in**. The receiver enables it by passing ``ssl_context=`` to
:class:`A2AServer`; the sender enables it by passing ``ssl_context=`` to
:func:`post_jsonrpc`. The default HTTP behaviour is unchanged so all
existing demos and tests continue to work without modification.

For production / cross-internet deployments, the recommended posture
remains Tailscale or WireGuard underneath. mTLS at the application layer
is for the case where neither is available.
"""

from __future__ import annotations

import datetime
import ipaddress
import os
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

#: Default cert validity. Self-signed; rotate by re-running gen-cert.
DEFAULT_VALIDITY_DAYS = 365

#: Default RSA key size. Ed25519 would be smaller / faster but RSA has
#: wider stdlib support and the cost is negligible at this scale.
DEFAULT_KEY_BITS = 3072


@dataclass(frozen=True)
class CertBundle:
    """A generated cert + key pair on disk."""

    agent_id: str
    cert_path: Path
    key_path: Path


def generate_self_signed_cert(
    agent_id: str,
    out_dir: Path,
    *,
    san_hostnames: Iterable[str] = ("localhost",),
    san_ips: Iterable[str] = ("127.0.0.1",),
    validity_days: int = DEFAULT_VALIDITY_DAYS,
    key_bits: int = DEFAULT_KEY_BITS,
) -> CertBundle:
    """Issue a self-signed cert + private key for ``agent_id``.

    The cert's CN is the agent_id. SAN entries cover ``localhost`` and
    ``127.0.0.1`` by default so handshakes against the local loopback
    succeed without extra plumbing.

    Files are written as ``<out_dir>/<agent_id>.crt`` (PEM) and
    ``<out_dir>/<agent_id>.key`` (PEM, no passphrase — protect with FS
    permissions, ``chmod 600``). Existing files are overwritten.
    """
    if not agent_id:
        raise ValueError("agent_id is required")
    out_dir.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=key_bits)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, agent_id)]
    )

    san: list[x509.GeneralName] = [x509.DNSName(agent_id)]
    for host in san_hostnames:
        san.append(x509.DNSName(host))
    for ip in san_ips:
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            # Skip malformed IPs without failing the whole issuance.
            continue

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=validity_days))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                x509.ExtendedKeyUsageOID.SERVER_AUTH,
                x509.ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=False,
        )
        .sign(private_key=key, algorithm=hashes.SHA256())
    )

    cert_path = out_dir / f"{agent_id}.crt"
    key_path = out_dir / f"{agent_id}.key"

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        # Best-effort on platforms that don't support chmod the same way.
        pass

    return CertBundle(agent_id=agent_id, cert_path=cert_path, key_path=key_path)


def load_trust_dir(trust_dir: Path) -> list[Path]:
    """Return every ``*.crt`` path under ``trust_dir`` (the trust set)."""
    if not trust_dir.exists():
        return []
    return sorted(trust_dir.glob("*.crt"))


def make_server_ssl_context(
    cert_path: Path,
    key_path: Path,
    client_trust_dir: Path,
) -> ssl.SSLContext:
    """Build an mTLS server context that requires + verifies client certs.

    Every PEM file in ``client_trust_dir`` becomes a trusted client root.
    Adding / removing files is the operator's mechanism for granting /
    revoking peer access.
    """
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    for ca_path in load_trust_dir(client_trust_dir):
        ctx.load_verify_locations(cafile=str(ca_path))
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = False  # peers are identified by cert subject (CN)
    return ctx


def make_client_ssl_context(
    cert_path: Path,
    key_path: Path,
    server_trust_dir: Path,
) -> ssl.SSLContext:
    """Build an mTLS client context that presents a cert + verifies the server."""
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    for ca_path in load_trust_dir(server_trust_dir):
        ctx.load_verify_locations(cafile=str(ca_path))
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = False  # SAN includes localhost + IP; CN is the agent_id
    return ctx


def is_mtls_enabled() -> bool:
    """Whether ``SYNAPSE_MTLS=1`` is set in the environment."""
    return os.environ.get("SYNAPSE_MTLS", "").lower() in {"1", "true", "yes"}


def extract_peer_common_name(ssl_object: ssl.SSLObject | ssl.SSLSocket) -> str:
    """Return the CN of the peer's cert, or ``""`` if not present.

    The CN is the agent_id by construction (see
    :func:`generate_self_signed_cert`). We use it to cross-check that the
    HMAC-asserted sender matches the TLS-asserted identity, closing the
    "stolen HMAC key over wire" attack.
    """
    peer = ssl_object.getpeercert()
    if not peer:
        return ""
    for rdn in peer.get("subject", ()):
        for key, value in rdn:
            if key == "commonName":
                return str(value)
    return ""
