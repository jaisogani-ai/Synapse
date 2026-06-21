# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Always-on secret detector — 140+ secret types + entropy fallback.

Wraps every file write / pre-commit / pre-push surface. 29 million secrets
leaked from AI tools in 2025; this detector is the first line of defence. It
combines a large catalog of provider-specific patterns (cloud, VCS, payments,
AI, messaging, observability, SaaS, crypto material) with a Shannon-entropy
fallback for unrecognised high-entropy tokens.

Matches are always **redacted** in findings — the raw secret never appears in a
report, a log, or memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from synapse.security.supply_chain import shannon_entropy

# Severity ladder, mirroring the project's code-review rule.
CRITICAL = "critical"
HIGH = "high"
MEDIUM = "medium"
LOW = "low"


@dataclass(frozen=True)
class SecretPattern:
    """A named secret pattern."""

    name: str
    provider: str
    pattern: re.Pattern
    severity: str


@dataclass(frozen=True)
class SecretFinding:
    """A detected (and redacted) secret."""

    name: str
    provider: str
    severity: str
    line: int
    preview: str


def _p(name: str, provider: str, regex: str, severity: str = HIGH) -> SecretPattern:
    """Compile a :class:`SecretPattern` (raises at import on a bad regex)."""
    return SecretPattern(name, provider, re.compile(regex), severity)


# fmt: off
SECRET_PATTERNS: tuple[SecretPattern, ...] = (
    # ---- Cloud providers ------------------------------------------------
    _p("AWS Access Key ID", "AWS", r"\bAKIA[0-9A-Z]{16}\b", CRITICAL),
    _p("AWS Session Token", "AWS", r"\bASIA[0-9A-Z]{16}\b", HIGH),
    _p("AWS Secret Access Key", "AWS", r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?[0-9a-zA-Z/+]{40}", HIGH),
    _p("AWS MWS Auth Token", "AWS", r"amzn\.mws\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", HIGH),
    _p("Google API Key", "GCP", r"\bAIza[0-9A-Za-z\-_]{35}\b", HIGH),
    _p("Google OAuth Client ID", "GCP", r"[0-9]+-[0-9A-Za-z_]{32}\.apps\.googleusercontent\.com", LOW),
    _p("Google OAuth Refresh Token", "GCP", r"\b1//[0-9A-Za-z\-_]{43,}", HIGH),
    _p("GCP Service Account", "GCP", r"\"type\":\s*\"service_account\"", MEDIUM),
    _p("Azure Storage Account Key", "Azure", r"(?i)AccountKey=[0-9A-Za-z+/]{86}==", HIGH),
    _p("Azure Client Secret", "Azure", r"(?i)client_secret\s*[=:]\s*['\"]?[0-9A-Za-z~._-]{30,}", MEDIUM),
    _p("Azure SAS Token", "Azure", r"(?i)sig=[0-9A-Za-z%]{43,}%3D", MEDIUM),
    _p("DigitalOcean PAT", "DigitalOcean", r"\bdop_v1_[0-9a-f]{64}\b", HIGH),
    _p("DigitalOcean OAuth Token", "DigitalOcean", r"\bdoo_v1_[0-9a-f]{64}\b", HIGH),
    _p("DigitalOcean Refresh Token", "DigitalOcean", r"\bdor_v1_[0-9a-f]{64}\b", HIGH),
    _p("Heroku API Key", "Heroku", r"(?i)heroku.{0,20}[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", MEDIUM),
    _p("Linode Token", "Linode", r"(?i)linode.{0,15}[0-9a-f]{64}", MEDIUM),
    _p("IBM Cloud IAM Key", "IBM", r"(?i)ibm.{0,15}[a-zA-Z0-9_\-]{44}", MEDIUM),
    _p("Alibaba Access Key", "Alibaba", r"\bLTAI[0-9A-Za-z]{12,20}\b", HIGH),
    _p("Tencent Cloud Secret ID", "Tencent", r"\bAKID[0-9A-Za-z]{13,40}\b", HIGH),
    _p("Cloudflare API Token", "Cloudflare", r"(?i)cloudflare.{0,15}[A-Za-z0-9_-]{40}", MEDIUM),
    _p("Cloudflare Global API Key", "Cloudflare", r"(?i)cf.{0,5}api.{0,5}key.{0,8}[0-9a-f]{37}", MEDIUM),
    _p("Oracle Cloud Key", "Oracle", r"(?i)oci.{0,15}[A-Za-z0-9]{40}", LOW),
    _p("Vultr API Key", "Vultr", r"(?i)vultr.{0,15}[A-Z0-9]{36}", LOW),
    # ---- VCS / git hosts ------------------------------------------------
    _p("GitHub PAT", "GitHub", r"\bghp_[0-9A-Za-z]{36}\b", CRITICAL),
    _p("GitHub OAuth Token", "GitHub", r"\bgho_[0-9A-Za-z]{36}\b", HIGH),
    _p("GitHub User-to-Server Token", "GitHub", r"\bghu_[0-9A-Za-z]{36}\b", HIGH),
    _p("GitHub Server-to-Server Token", "GitHub", r"\bghs_[0-9A-Za-z]{36}\b", HIGH),
    _p("GitHub Refresh Token", "GitHub", r"\bghr_[0-9A-Za-z]{36}\b", HIGH),
    _p("GitHub Fine-Grained PAT", "GitHub", r"\bgithub_pat_[0-9A-Za-z_]{82}\b", CRITICAL),
    _p("GitLab PAT", "GitLab", r"\bglpat-[0-9A-Za-z_\-]{20}\b", HIGH),
    _p("GitLab Pipeline Trigger", "GitLab", r"\bglptt-[0-9a-f]{40}\b", HIGH),
    _p("GitLab Runner Registration", "GitLab", r"\bGR1348941[0-9A-Za-z_\-]{20}\b", HIGH),
    _p("GitLab CI Build Token", "GitLab", r"\bglcbt-[0-9A-Za-z_\-]{20,}\b", MEDIUM),
    _p("Bitbucket Credential", "Bitbucket", r"(?i)bitbucket.{0,15}[A-Za-z0-9]{20,}", LOW),
    _p("Atlassian API Token", "Atlassian", r"\bATATT[A-Za-z0-9_\-=]{20,}\b", HIGH),
    # ---- Messaging / comms ----------------------------------------------
    _p("Slack Token", "Slack", r"\bxox[baprs]-[0-9A-Za-z-]{10,48}\b", HIGH),
    _p("Slack App-Level Token", "Slack", r"\bxapp-[0-9]-[A-Z0-9]+-[0-9]+-[0-9a-f]+\b", HIGH),
    _p("Slack Webhook", "Slack", r"https://hooks\.slack\.com/services/T[0-9A-Za-z_]+/B[0-9A-Za-z_]+/[0-9A-Za-z]+", HIGH),
    _p("Discord Bot Token", "Discord", r"\b[MNO][A-Za-z\d_-]{23,25}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,38}\b", HIGH),
    _p("Discord Webhook", "Discord", r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/[0-9]{17,20}/[0-9A-Za-z_-]{60,68}", HIGH),
    _p("Telegram Bot Token", "Telegram", r"\b\d{8,10}:[0-9A-Za-z_-]{35}\b", HIGH),
    _p("Twilio Account SID", "Twilio", r"\bAC[0-9a-f]{32}\b", HIGH),
    _p("Twilio API Key SID", "Twilio", r"\bSK[0-9a-f]{32}\b", HIGH),
    _p("Twilio Auth Token", "Twilio", r"(?i)twilio.{0,15}[0-9a-f]{32}", MEDIUM),
    _p("SendGrid API Key", "SendGrid", r"\bSG\.[0-9A-Za-z_-]{22}\.[0-9A-Za-z_-]{43}\b", CRITICAL),
    _p("Mailgun API Key", "Mailgun", r"\bkey-[0-9a-f]{32}\b", HIGH),
    _p("Mailchimp API Key", "Mailchimp", r"\b[0-9a-f]{32}-us[0-9]{1,2}\b", HIGH),
    _p("Postmark Server Token", "Postmark", r"(?i)postmark.{0,15}[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", MEDIUM),
    _p("Nexmo/Vonage Key", "Vonage", r"(?i)(?:nexmo|vonage).{0,15}[0-9a-f]{8}", LOW),
    _p("MessageBird Key", "MessageBird", r"(?i)messagebird.{0,15}[0-9A-Za-z]{25}", LOW),
    _p("Plivo Auth ID", "Plivo", r"(?i)plivo.{0,15}[A-Z]{20}", LOW),
    _p("Microsoft Teams Webhook", "Teams", r"https://[a-z0-9]+\.webhook\.office\.com/webhookb2/[0-9a-f-]+@[0-9a-f-]+/IncomingWebhook/[0-9a-f]+/[0-9a-f-]+", MEDIUM),
    # ---- Payments / commerce --------------------------------------------
    _p("Stripe Live Secret Key", "Stripe", r"\bsk_live_[0-9A-Za-z]{24,99}\b", CRITICAL),
    _p("Stripe Restricted Key", "Stripe", r"\brk_live_[0-9A-Za-z]{24,99}\b", CRITICAL),
    _p("Stripe Publishable Key", "Stripe", r"\bpk_live_[0-9A-Za-z]{24,99}\b", LOW),
    _p("Stripe Test Secret Key", "Stripe", r"\bsk_test_[0-9A-Za-z]{24,99}\b", MEDIUM),
    _p("Square Access Token", "Square", r"\bsq0atp-[0-9A-Za-z_-]{22}\b", HIGH),
    _p("Square OAuth Secret", "Square", r"\bsq0csp-[0-9A-Za-z_-]{43}\b", HIGH),
    _p("Square Production Token", "Square", r"\bEAAA[0-9A-Za-z_-]{60}\b", HIGH),
    _p("Braintree/PayPal Token", "PayPal", r"\baccess_token\$production\$[0-9a-z]{16}\$[0-9a-f]{32}\b", HIGH),
    _p("Razorpay Key ID", "Razorpay", r"\brzp_live_[0-9A-Za-z]{14,}\b", HIGH),
    _p("Adyen API Key", "Adyen", r"(?i)adyen.{0,15}AQE[0-9A-Za-z]{20,}", LOW),
    _p("Coinbase Key", "Coinbase", r"(?i)coinbase.{0,15}[0-9A-Za-z]{32}", LOW),
    _p("Plaid Secret", "Plaid", r"(?i)plaid.{0,15}[0-9a-f]{24,32}", LOW),
    _p("Shopify Access Token", "Shopify", r"\bshpat_[0-9a-fA-F]{32}\b", HIGH),
    _p("Shopify Custom App Token", "Shopify", r"\bshpca_[0-9a-fA-F]{32}\b", HIGH),
    _p("Shopify Private App Token", "Shopify", r"\bshppa_[0-9a-fA-F]{32}\b", HIGH),
    _p("Shopify Shared Secret", "Shopify", r"\bshpss_[0-9a-fA-F]{32}\b", HIGH),
    # ---- AI / ML providers ----------------------------------------------
    _p("OpenAI API Key", "OpenAI", r"\bsk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}\b", CRITICAL),
    _p("OpenAI Project Key", "OpenAI", r"\bsk-proj-[A-Za-z0-9_-]{20,}\b", CRITICAL),
    _p("OpenAI Legacy Key", "OpenAI", r"\bsk-[A-Za-z0-9]{48}\b", HIGH),
    _p("Anthropic API Key", "Anthropic", r"\bsk-ant-[A-Za-z0-9-]{20,}\b", CRITICAL),
    _p("Anthropic Admin Key", "Anthropic", r"\bsk-ant-admin[0-9]{2}-[A-Za-z0-9_-]{20,}\b", CRITICAL),
    _p("HuggingFace Token", "HuggingFace", r"\bhf_[A-Za-z0-9]{34}\b", HIGH),
    _p("Replicate Token", "Replicate", r"\br8_[A-Za-z0-9]{37}\b", HIGH),
    _p("Cohere API Key", "Cohere", r"(?i)cohere.{0,15}[A-Za-z0-9]{40}", MEDIUM),
    _p("Perplexity API Key", "Perplexity", r"\bpplx-[A-Za-z0-9]{32,}\b", HIGH),
    _p("Groq API Key", "Groq", r"\bgsk_[A-Za-z0-9]{20,}\b", HIGH),
    _p("Mistral API Key", "Mistral", r"(?i)mistral.{0,15}[A-Za-z0-9]{32}", MEDIUM),
    _p("Together AI Key", "Together", r"(?i)together.{0,15}[0-9a-f]{64}", LOW),
    _p("DeepSeek Key", "DeepSeek", r"(?i)deepseek.{0,15}sk-[A-Za-z0-9]{32}", LOW),
    _p("LangSmith API Key", "LangChain", r"\blsv2_(?:pt|sk)_[A-Za-z0-9]{32}_[A-Za-z0-9]{10}\b", HIGH),
    _p("OpenRouter Key", "OpenRouter", r"\bsk-or-v1-[0-9a-f]{64}\b", HIGH),
    # ---- Dev tools / registries / CI ------------------------------------
    _p("npm Token", "npm", r"\bnpm_[A-Za-z0-9]{36}\b", HIGH),
    _p("PyPI Token", "PyPI", r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{50,}\b", CRITICAL),
    _p("RubyGems Token", "RubyGems", r"\brubygems_[0-9a-f]{48}\b", HIGH),
    _p("Docker Hub PAT", "Docker", r"\bdckr_pat_[A-Za-z0-9_-]{27,}\b", HIGH),
    _p("crates.io Token", "crates.io", r"\bcio[0-9A-Za-z]{32}\b", HIGH),
    _p("NuGet API Key", "NuGet", r"\boy2[a-z0-9]{43}\b", HIGH),
    _p("Terraform Cloud Token", "Terraform", r"\b[A-Za-z0-9]{14}\.atlasv1\.[A-Za-z0-9_-]{60,}\b", HIGH),
    _p("Vercel Token", "Vercel", r"(?i)vercel.{0,15}[A-Za-z0-9]{24}", LOW),
    _p("Netlify Token", "Netlify", r"(?i)netlify.{0,15}[A-Za-z0-9_-]{40,}", LOW),
    _p("CircleCI PAT", "CircleCI", r"\bCCIPAT_[A-Za-z0-9]{12,}_[A-Za-z0-9]{40}\b", HIGH),
    _p("Travis CI Token", "Travis", r"(?i)travis.{0,15}[A-Za-z0-9]{22}", LOW),
    _p("Buildkite Agent Token", "Buildkite", r"(?i)buildkite.{0,15}[0-9a-f]{40}", LOW),
    _p("Codecov Token", "Codecov", r"(?i)codecov.{0,15}[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", LOW),
    _p("SonarQube Token", "SonarQube", r"\bsq[apu]_[0-9a-f]{40}\b", HIGH),
    _p("JFrog Token", "JFrog", r"(?i)jfrog.{0,15}[A-Za-z0-9]{64}", LOW),
    _p("Algolia Admin Key", "Algolia", r"(?i)algolia.{0,15}[A-Za-z0-9]{32}", LOW),
    # ---- Observability / monitoring -------------------------------------
    _p("Datadog API Key", "Datadog", r"(?i)datadog.{0,15}[0-9a-f]{32}", MEDIUM),
    _p("Datadog App Key", "Datadog", r"(?i)datadog.{0,15}[0-9a-f]{40}", LOW),
    _p("New Relic API Key", "NewRelic", r"\bNRAK-[A-Z0-9]{27}\b", HIGH),
    _p("New Relic User Key", "NewRelic", r"\bNRJS-[a-f0-9]{19}\b", MEDIUM),
    _p("Sentry DSN", "Sentry", r"https://[0-9a-f]{32}@[0-9a-z.-]+/[0-9]+", MEDIUM),
    _p("PagerDuty Token", "PagerDuty", r"(?i)pagerduty.{0,15}[0-9a-zA-Z_+-]{20}", LOW),
    _p("Grafana Service Account", "Grafana", r"\bglsa_[A-Za-z0-9]{32}_[0-9a-f]{8}\b", HIGH),
    _p("Grafana Cloud Token", "Grafana", r"\bglc_[A-Za-z0-9+/=]{30,}\b", HIGH),
    _p("Rollbar Token", "Rollbar", r"(?i)rollbar.{0,15}[0-9a-f]{32}", LOW),
    _p("Bugsnag Key", "Bugsnag", r"(?i)bugsnag.{0,15}[0-9a-f]{32}", LOW),
    _p("Honeycomb Key", "Honeycomb", r"(?i)honeycomb.{0,15}[A-Za-z0-9]{22}", LOW),
    _p("Dynatrace Token", "Dynatrace", r"\bdt0c01\.[A-Z0-9]{24}\.[A-Z0-9]{64}\b", HIGH),
    _p("Splunk Token", "Splunk", r"(?i)splunk.{0,15}[A-Za-z0-9]{22}", LOW),
    # ---- SaaS / productivity --------------------------------------------
    _p("Notion Integration Token", "Notion", r"\b(?:secret_|ntn_)[A-Za-z0-9]{36,}\b", HIGH),
    _p("Linear API Key", "Linear", r"\blin_api_[A-Za-z0-9]{40}\b", HIGH),
    _p("Airtable PAT", "Airtable", r"\bpat[A-Za-z0-9]{14}\.[0-9a-f]{64}\b", HIGH),
    _p("Airtable Legacy Key", "Airtable", r"\bkey[A-Za-z0-9]{14}\b", MEDIUM),
    _p("Asana PAT", "Asana", r"\b[0-9]/[0-9]{16}:[0-9a-f]{32}\b", MEDIUM),
    _p("Figma Token", "Figma", r"\bfigd_[A-Za-z0-9_-]{40,}\b", HIGH),
    _p("Dropbox Token", "Dropbox", r"\bsl\.[A-Za-z0-9_-]{130,}\b", HIGH),
    _p("Box Token", "Box", r"(?i)box.{0,15}[A-Za-z0-9]{32}", LOW),
    _p("Zoom S2S Token", "Zoom", r"(?i)zoom.{0,15}[A-Za-z0-9_-]{22}", LOW),
    _p("Intercom Token", "Intercom", r"(?i)intercom.{0,15}[A-Za-z0-9=_-]{40,}", LOW),
    _p("Segment Write Key", "Segment", r"(?i)segment.{0,15}[A-Za-z0-9]{32}", LOW),
    _p("Amplitude Key", "Amplitude", r"(?i)amplitude.{0,15}[0-9a-f]{32}", LOW),
    _p("Mixpanel Token", "Mixpanel", r"(?i)mixpanel.{0,15}[0-9a-f]{32}", LOW),
    _p("LaunchDarkly SDK Key", "LaunchDarkly", r"\b(?:sdk|api|mob)-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", MEDIUM),
    _p("Optimizely Token", "Optimizely", r"(?i)optimizely.{0,15}[0-9A-Za-z:_-]{40,}", LOW),
    _p("Contentful Token", "Contentful", r"\bCFPAT-[A-Za-z0-9_-]{43}\b", HIGH),
    _p("Firebase Cloud Messaging Key", "Firebase", r"\bAAAA[A-Za-z0-9_-]{7}:[A-Za-z0-9_-]{140,}\b", HIGH),
    _p("Okta Token", "Okta", r"(?i)okta.{0,15}00[A-Za-z0-9_-]{40}", MEDIUM),
    _p("Auth0 Client Secret", "Auth0", r"(?i)auth0.{0,15}[A-Za-z0-9_-]{40,}", LOW),
    _p("Clerk Secret Key", "Clerk", r"\bsk_live_[A-Za-z0-9]{40,}\b", HIGH),
    _p("Supabase Service Key", "Supabase", r"(?i)supabase.{0,15}eyJ[A-Za-z0-9_-]{20,}", MEDIUM),
    # ---- Database connection strings ------------------------------------
    _p("PostgreSQL URL", "Database", r"postgres(?:ql)?://[^:\s]+:[^@\s]+@[^/\s]+", HIGH),
    _p("MySQL URL", "Database", r"mysql://[^:\s]+:[^@\s]+@[^/\s]+", HIGH),
    _p("MongoDB URL", "Database", r"mongodb(?:\+srv)?://[^:\s]+:[^@\s]+@[^/\s]+", HIGH),
    _p("Redis URL", "Database", r"redis://[^:\s]*:[^@\s]+@[^/\s]+", HIGH),
    _p("AMQP URL", "Database", r"amqps?://[^:\s]+:[^@\s]+@[^/\s]+", HIGH),
    # ---- Crypto material / generic --------------------------------------
    _p("RSA Private Key", "Crypto", r"-----BEGIN RSA PRIVATE KEY-----", CRITICAL),
    _p("OpenSSH Private Key", "Crypto", r"-----BEGIN OPENSSH PRIVATE KEY-----", CRITICAL),
    _p("DSA Private Key", "Crypto", r"-----BEGIN DSA PRIVATE KEY-----", CRITICAL),
    _p("EC Private Key", "Crypto", r"-----BEGIN EC PRIVATE KEY-----", CRITICAL),
    _p("PGP Private Key", "Crypto", r"-----BEGIN PGP PRIVATE KEY BLOCK-----", CRITICAL),
    _p("Generic Private Key", "Crypto", r"-----BEGIN PRIVATE KEY-----", CRITICAL),
    _p("Encrypted Private Key", "Crypto", r"-----BEGIN ENCRYPTED PRIVATE KEY-----", CRITICAL),
    _p("PuTTY Private Key", "Crypto", r"PuTTY-User-Key-File-[23]:", HIGH),
    _p("Certificate", "Crypto", r"-----BEGIN CERTIFICATE-----", LOW),
    _p("JSON Web Token", "Generic", r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b", MEDIUM),
    _p("Basic Auth in URL", "Generic", r"(?i)://[^/\s:@]{3,}:[^/\s:@]{3,}@", HIGH),
    _p("Generic API Key Assignment", "Generic", r"(?i)(?:api[_-]?key|apikey)\s*[=:]\s*['\"][0-9a-zA-Z\-_]{16,}['\"]", MEDIUM),
    _p("Generic Secret Assignment", "Generic", r"(?i)(?:secret|token|passwd|password|pwd)\s*[=:]\s*['\"][^'\"]{8,}['\"]", MEDIUM),
    _p("Generic Bearer Token", "Generic", r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}=*", LOW),
)
# fmt: on

#: Tokens considered for the entropy fallback.
_GENERIC_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_\-]{24,}")
#: Entropy (bits/char) above which an unrecognised token is flagged.
ENTROPY_THRESHOLD = 4.3


def redact(secret: str) -> str:
    """Return a safe preview of ``secret`` (never the full value)."""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}…[redacted:{len(secret)} chars]"


def detect(content: str, *, include_entropy: bool = True) -> list[SecretFinding]:
    """Scan ``content`` line-by-line and return redacted :class:`SecretFinding`s."""
    findings: list[SecretFinding] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        matched_spans: list[tuple[int, int]] = []
        for spec in SECRET_PATTERNS:
            match = spec.pattern.search(line)
            if match:
                matched_spans.append(match.span())
                findings.append(
                    SecretFinding(
                        name=spec.name,
                        provider=spec.provider,
                        severity=spec.severity,
                        line=line_no,
                        preview=redact(match.group(0)),
                    )
                )
        if include_entropy:
            findings.extend(_entropy_findings(line, line_no, matched_spans))
    return findings


def _entropy_findings(
    line: str, line_no: int, matched_spans: list[tuple[int, int]]
) -> list[SecretFinding]:
    """Flag high-entropy tokens not already captured by a named pattern."""
    out: list[SecretFinding] = []
    for token_match in _GENERIC_TOKEN_RE.finditer(line):
        if _overlaps(token_match.span(), matched_spans):
            continue
        token = token_match.group(0)
        if shannon_entropy(token) >= ENTROPY_THRESHOLD:
            out.append(
                SecretFinding(
                    name="High-Entropy String",
                    provider="Entropy",
                    severity=LOW,
                    line=line_no,
                    preview=redact(token),
                )
            )
    return out


def _overlaps(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    """Whether ``span`` overlaps any span in ``spans``."""
    start, end = span
    return any(start < e and s < end for s, e in spans)


def has_secrets(content: str) -> bool:
    """Whether ``content`` contains at least one detectable secret."""
    return bool(detect(content, include_entropy=False))


def scan_file(path: str) -> list[SecretFinding]:
    """Scan a file at ``path`` (UTF-8, errors ignored)."""
    with open(path, encoding="utf-8", errors="ignore") as handle:
        return detect(handle.read())
