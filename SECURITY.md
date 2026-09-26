# Security Policy

## Reporting a Vulnerability

Please report security issues privately to the maintainers rather than opening a
public issue. Include a description, reproduction steps and impact assessment.

## Security Practices

ProxyAtlas is built with the following protections:

- **Input validation** - all imported proxy data and provider responses are
  parsed defensively; malformed records are rejected cleanly and never executed
  as commands.
- **Parameterized database access** - all queries go through SQLAlchemy; no raw
  string SQL is constructed from user input.
- **Credential protection** - proxy credentials and provider API keys are
  encrypted at rest with Fernet (per-install key, or `PROXYATLAS_SECRET_KEY`).
  Plaintext credentials are never stored unnecessarily.
- **No secrets in logs** - a redaction filter scrubs passwords, tokens and
  `user:pass@` credentials from every log record.
- **Sanitized reports** - all dynamic content in HTML reports/exports is
  HTML-escaped to prevent injection.
- **Response size caps** - feed/API responses are size-limited to avoid resource
  exhaustion from hostile sources.
- **Provider isolation** - a failing intelligence/discovery provider is caught
  and reported; it never aborts a batch job.
- **Fault tolerance** - a single bad proxy or provider never terminates a
  discovery or validation job.

## Responsible Use

ProxyAtlas is a network utility intended for authorized testing and management of
proxy infrastructure you own or are permitted to assess. The Internet Discovery
module operates only over CIDR ranges you explicitly configure and skips
private/reserved space. Use it only against address space you are authorized to
probe and in accordance with applicable law.
