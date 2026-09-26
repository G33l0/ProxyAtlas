# Discovery

Discovery collects proxy *candidates*. Candidates are never trusted as working
until they pass validation - they carry `validation_status = DISCOVERED` and sit
in the discovery queue.

## Supported formats

The parser/normalizer accept:

- `IP:PORT`
- `IP:PORT:USERNAME:PASSWORD`
- `PROTOCOL://IP:PORT`
- `PROTOCOL://USERNAME:PASSWORD@IP:PORT`
- Bracketed IPv6 (`[2001:db8::1]:8080`, `proto://[..]:port`)
- Hostnames (`proxy.example.com:3128`)

Files may be TXT (one per line), CSV (`host,port[,protocol[,user,pass]]` or one
proxy string per row) or JSON (list of strings or objects with
`host`/`port`/`protocol`/`username`/`password`, or a `proxies` array).

Malformed records are rejected cleanly and reported; they never crash the app.

## Source types

1. **User-imported files** - TXT/CSV/JSON via the Discovery page or `Ctrl+I`.
2. **Feeds** - a configurable URL returning proxy data.
3. **APIs** - JSON APIs with optional auth header and a `records_key` path.
4. **Custom/plugin adapters** - inline lists or drop-in plugin modules.
5. **Internet Discovery** - generates candidates across explicitly configured,
   authorized CIDR ranges combined with common proxy ports. Generation is
   bounded by `max_candidates` and skips private/reserved space.

All sources funnel through the same normalization + deduplication and enter the
**same** validation pipeline - there is no separate validation path for any
source, including Internet Discovery.

## Deduplication

Candidates are deduplicated by endpoint identity (`protocol://host:port`).
Credentials from a richer duplicate upgrade a bare one; contributing sources are
merged into `metadata['sources']`.

## Scheduling

`app/discovery/scheduler.py` computes which sources/monitors are due based on an
interval and last-run time; the services layer triggers them.

## Validation tuning (retry & protocol auto-detection)

Two Settings -> Testing options improve real-world yield without ever creating
false positives (a proxy is WORKING only after a genuine proxied request returns
a valid exit IP):

- **Retries / retry backoff** - transient failures (timeout, connection,
  protocol, no-exit-IP) are re-attempted with exponential backoff. Authentication
  failures are terminal and never retried.
- **Protocol auto-detect** - for scheme-less or mislabeled candidates, the
  validator tries the candidate's own protocol first and only falls back to the
  others (HTTP -> SOCKS5 -> SOCKS4 -> HTTPS) if it fails, adopting the protocol that
  genuinely works.
