// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * `backend.design_auth` — generate an auth system scaffold.
 *
 * Produces real, runnable starter code for the requested combination of
 * methods (JWT, OAuth, magic-link, SSO) and provider (auth0, clerk, supabase,
 * or self-hosted "custom"). Output is plain files; the caller writes them.
 */

import type { AuthMethod, AuthProvider, GeneratedFile } from "./types.ts";

/** Options for {@link designAuth}. */
export interface AuthOptions {
  methods: AuthMethod[];
  provider?: AuthProvider;
  multi_tenancy?: boolean;
}

const DEFAULT_PROVIDER: AuthProvider = "custom";

/** Build the auth system files. */
export function designAuth(options: AuthOptions): GeneratedFile[] {
  if (!options.methods || options.methods.length === 0) {
    throw new Error("at least one auth method is required");
  }
  const provider = options.provider ?? DEFAULT_PROVIDER;
  const files: GeneratedFile[] = [readmeFor(options, provider), envExample(provider)];

  for (const method of options.methods) {
    if (method === "jwt") files.push(jwtFile(options.multi_tenancy ?? false));
    if (method === "oauth") files.push(oauthFile(provider));
    if (method === "magic_link") files.push(magicLinkFile());
    if (method === "sso") files.push(ssoFile(provider));
  }
  return files;
}

function readmeFor(options: AuthOptions, provider: AuthProvider): GeneratedFile {
  return {
    path: "auth/README.md",
    contents: `# Auth scaffold\n\nMethods: ${options.methods.join(", ")}\nProvider: ${provider}\nMulti-tenant: ${options.multi_tenancy ? "yes" : "no"}\n`,
  };
}

function envExample(provider: AuthProvider): GeneratedFile {
  const lines = [
    "JWT_SECRET=change-me",
    "JWT_ISSUER=synapse",
    "JWT_AUDIENCE=synapse-clients",
    "OAUTH_CLIENT_ID=",
    "OAUTH_CLIENT_SECRET=",
    "OAUTH_REDIRECT_URI=http://localhost:3000/auth/callback",
  ];
  if (provider === "auth0") lines.push("AUTH0_DOMAIN=your-tenant.auth0.com");
  if (provider === "clerk") lines.push("CLERK_PUBLISHABLE_KEY=", "CLERK_SECRET_KEY=");
  if (provider === "supabase") lines.push("SUPABASE_URL=", "SUPABASE_ANON_KEY=");
  return { path: "auth/.env.example", contents: lines.join("\n") + "\n" };
}

function jwtFile(multiTenant: boolean): GeneratedFile {
  return {
    path: "auth/jwt.py",
    contents: `# SPDX-License-Identifier: Apache-2.0
"""HS256 JWT issuance + verification."""
from datetime import datetime, timedelta, timezone
import os

from jose import JWTError, jwt


SECRET = os.environ.get("JWT_SECRET", "change-me")
ISSUER = os.environ.get("JWT_ISSUER", "synapse")
AUDIENCE = os.environ.get("JWT_AUDIENCE", "synapse-clients")


def issue_token(subject: str${multiTenant ? ", tenant_id: str" : ""}, ttl_minutes: int = 15) -> str:
    """Issue a short-lived JWT for 'subject'${multiTenant ? " in 'tenant_id'." : "."}"""
    payload = {
        "sub": subject,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
        ${multiTenant ? '"tenant": tenant_id,\n        ' : ""}
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def verify_token(token: str) -> dict:
    """Verify 'token' and return its decoded claims, or raise 'ValueError'."""
    try:
        return jwt.decode(token, SECRET, algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER)
    except JWTError as exc:
        raise ValueError(f"invalid token: {exc}") from exc
`,
  };
}

function oauthFile(provider: AuthProvider): GeneratedFile {
  return {
    path: "auth/oauth.py",
    contents: `# SPDX-License-Identifier: Apache-2.0
"""OAuth 2.0 authorization-code flow (${provider})."""
import os
import secrets
import urllib.parse

CLIENT_ID = os.environ["OAUTH_CLIENT_ID"]
REDIRECT_URI = os.environ["OAUTH_REDIRECT_URI"]
AUTH_URL = "https://accounts.example.com/o/oauth2/auth"
TOKEN_URL = "https://accounts.example.com/o/oauth2/token"


def authorize_url(scope: str = "openid email profile") -> tuple[str, str]:
    """Build the authorization URL and a CSRF state value."""
    state = secrets.token_urlsafe(32)
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": scope,
        "state": state,
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}", state
`,
  };
}

function magicLinkFile(): GeneratedFile {
  return {
    path: "auth/magic_link.py",
    contents: `# SPDX-License-Identifier: Apache-2.0
"""Magic-link issuance + verification."""
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

SECRET = os.environ.get("JWT_SECRET", "change-me").encode()


def issue_magic_link(email: str, base_url: str, ttl_minutes: int = 15) -> str:
    """Build a one-time login URL for 'email'."""
    nonce = secrets.token_urlsafe(24)
    expires = int((datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).timestamp())
    payload = f"{email}.{nonce}.{expires}"
    signature = hmac.new(SECRET, payload.encode(), "sha256").hexdigest()
    return f"{base_url}/auth/magic?p={payload}&s={signature}"


def verify_magic_link(payload: str, signature: str, now: datetime | None = None) -> str | None:
    """Return the email if the link is valid + unexpired, else 'None'."""
    expected = hmac.new(SECRET, payload.encode(), "sha256").hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    email, _nonce, expires_str = payload.split(".")
    current = now or datetime.now(timezone.utc)
    if current.timestamp() >= int(expires_str):
        return None
    return email
`,
  };
}

function ssoFile(provider: AuthProvider): GeneratedFile {
  return {
    path: "auth/sso.py",
    contents: `# SPDX-License-Identifier: Apache-2.0
"""SAML/OIDC SSO entrypoints (${provider})."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SsoConfig:
    """Per-tenant SSO configuration."""

    tenant: str
    idp_metadata_url: str
    acs_url: str  # assertion consumer service


def begin_login(config: SsoConfig) -> str:
    """Return the URL the user is redirected to to start SSO."""
    return f"{config.idp_metadata_url}?acs={config.acs_url}&tenant={config.tenant}"
`,
  };
}
