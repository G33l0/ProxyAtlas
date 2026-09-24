# Database

ProxyAtlas uses **SQLite** via **SQLAlchemy 2.0**, with **Alembic** migrations
run programmatically at startup.

## Location

By default the database lives in the per-user data directory:

- Windows: `%APPDATA%\ProxyAtlas\proxyatlas.sqlite`
- macOS: `~/Library/Application Support/ProxyAtlas/proxyatlas.sqlite`
- Linux: `~/.local/share/ProxyAtlas/proxyatlas.sqlite`

Override the whole data directory with `PROXYATLAS_DATA_DIR`, or set a custom
database path under **Settings → Database**.

## Engine tuning

SQLite connections are configured with WAL journaling, `foreign_keys=ON`,
`synchronous=NORMAL` and a busy timeout, so reads and writes coexist while the
GUI stays responsive.

## Models

| Model | Purpose |
|-------|---------|
| `Proxy` | canonical validated endpoint (unique on protocol+host+port) |
| `ProxyEndpoint` | raw discovery record |
| `ProxyCredential` | encrypted credentials |
| `ProxyTest` / `ProxyTestResult` | validation runs and granular metrics |
| `ProxyHistory` | time-series snapshots for history/monitoring charts |
| `ProxySource` | configured discovery source |
| `DiscoveryJob` / `DiscoveryResult` | discovery jobs and the candidate queue |
| `MonitoringJob` / `MonitoringResult` | monitoring configuration and results |
| `NetworkIdentity` / `GeoLocation` | cached intelligence by IP |
| `ApplicationSetting` | collections, saved filters, key/value state |
| `ExportJob` | export/report history |
| `AuditLog` | notable actions |

Indexes cover status, classification, country, protocol, score and
last-checked; a unique constraint on `(protocol, host, port)` prevents duplicate
proxies. Deduplication uses endpoint identity rather than blind inserts.

## Migrations

The initial revision (`app/database/migrations/versions/0001_initial.py`)
materializes the model metadata. Run migrations manually with:

```bash
alembic upgrade head
```

The application also runs `run_migrations()` on startup and falls back to
`create_all` if Alembic is unavailable.
