# Providers

ProxyAtlas has two provider families, each behind a small interface so new ones
can be added without touching the core.

## Discovery providers

Interface: `app/discovery/base.py :: DiscoveryProvider`

Methods: `name()`, `description()`, `configure(config)`,
`validate_configuration()`, `metadata()`, `config_schema()`, and the async
`discover()` generator that yields `ProxyCandidate` objects.

Built-in providers (`app/discovery/providers/`):

| Key        | Provider                    | Config fields |
|------------|-----------------------------|---------------|
| `file`     | `FileProvider`              | `path`, `default_protocol` |
| `feed`     | `FeedProvider`              | `url`, `format`, `default_protocol`, `timeout` |
| `api`      | `ApiProvider`               | `url`, `auth_header`, `auth_value`, `records_key`, `default_protocol`, `timeout` |
| `custom`   | `CustomListProvider`        | `entries`, `default_protocol` |
| `internet` | `InternetDiscoveryProvider` | `cidrs`, `ports`, `max_candidates`, `shuffle`, `profile` |

Register a new provider with `DiscoveryManager.register_provider(key, cls)`, or
drop a plugin module in `app/discovery/providers/future_providers/` exposing
`build(config) -> DiscoveryProvider` or a `PROVIDER` class, and load it via
`app/discovery/providers/custom_provider.py :: load_plugin_provider`.

## Intelligence providers

Interface: `app/intelligence/base.py :: IntelligenceProvider`

Methods: `name()`, `description()`, `configure(config)`,
`validate_configuration()`, `metadata()`, and the async `lookup(ip)` returning
an `IntelligenceResult`.

Built-in providers (`app/intelligence/providers/`):

| Name      | Kind    | Notes |
|-----------|---------|-------|
| `ip-api`  | geoip   | ip-api.com, free, no key |
| `ipinfo`  | geoip   | ipinfo.io, optional token (`IPINFO_TOKEN` or Settings → Providers) |
| `builtin` | network | offline reverse-DNS + hosting heuristics, always available |

The `IntelligenceManager` runs enabled providers in priority order and merges
non-empty fields. A provider failure is recorded in its status and never stops
the lookup or the validation pipeline.

## Credentials & secrets

- Provider API keys are configured under **Settings → Providers** (or via
  environment variables) and are **never hard-coded**.
- Proxy credentials and stored secrets are encrypted at rest (Fernet).
- Nothing sensitive is written to logs (redaction filter).

## Offline GeoIP (MMDB)

The `mmdb` provider (`app/intelligence/providers/mmdb.py`) resolves geolocation
and ASN/ISP from local MaxMind GeoLite2 or DB-IP `.mmdb` files using `geoip2`,
with **no network calls and no rate limits**. Configure it under
Settings → Providers:

| Field | Purpose |
|-------|---------|
| `city_db` | Path to GeoLite2-City / GeoLite2-Country (or DB-IP) `.mmdb` |
| `asn_db`  | Path to GeoLite2-ASN (or DB-IP ASN) `.mmdb` |
| `enabled` | Auto-enabled when a database path is set |

It runs at the highest priority, so when present it answers first and the online
providers only fill gaps. ProxyAtlas does not bundle these licensed databases;
download them from MaxMind or DB-IP. If `geoip2` is not installed or no database
is configured, the provider returns nothing and the pipeline continues.
