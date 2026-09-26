<div align="center">

<img src="assets/logo/proxyatlas_logo.png" alt="ProxyAtlas" width="440">

**Discover. Validate. Analyze. Manage.**

A professional PyQt6 desktop application for discovering proxy endpoints from
configurable sources, validating them, identifying their characteristics,
classifying them, monitoring their availability, and providing searchable,
exportable results.

</div>

---

## Overview

ProxyAtlas turns raw proxy candidates from many sources into a continuously
updated database of **validated** proxy endpoints. It clearly separates
**discovered** candidates from **validated** endpoints — a proxy appearing in a
source is only ever a candidate until it passes the validation pipeline.

It supports multiple proxy **categories** (Residential, Mobile, Datacenter, ISP,
Business, Educational, Government, Unknown) and **protocols** (HTTP, HTTPS,
SOCKS4, SOCKS5), and is architected so the discovery, validation, intelligence,
classification, monitoring and UI subsystems can evolve independently.

## Features

- **Modular discovery engine** — file (TXT/CSV/JSON), feed URLs, JSON APIs,
  custom/plugin adapters, and an **Internet Discovery** module that generates
  candidates over authorized CIDR ranges. Every source feeds the *same*
  validation pipeline.
- **Real validation engine** — genuine proxy-mediated requests over
  HTTP/HTTPS/SOCKS4/SOCKS5 with exit-IP detection, latency, reliability,
  anonymity and DNS analysis. A responding TCP port is never enough to be
  "working".
- **Validation profiles** — Quick / Standard / Deep, plus custom profiles.
- **Controlled concurrency** — bounded async workers, never a thread per proxy;
  the GUI thread never blocks. Live totals, success rate, latency and throughput.
- **Pause / Resume / Stop** for every major job.
- **IP intelligence** — pluggable providers (ip-api.com, ipinfo.io, and an
  offline reverse-DNS/hosting-heuristic provider) for geolocation, ASN, ISP,
  organization and hosting indicators.
- **Evidence-based classification** — never "not datacenter = residential";
  every verdict stores its confidence and supporting evidence.
- **Explainable quality scoring** — connectivity, latency, reliability,
  stability and freshness components you can inspect.
- **Persistent SQLite database** (SQLAlchemy + Alembic) with identity-based
  deduplication and indexes.
- **Advanced filtering** — protocol, country, ISP, ASN, classification,
  anonymity, latency, reliability, uptime, score, source, and free-text search,
  combinable with AND/OR, saveable as filters and **collections**.
- **Professional results table** — sorting, searching, multi-selection, column
  visibility, context menu, copy/re-test/export/tag/details, pagination.
- **Monitoring** — track collections/filters/proxies on a schedule with history
  charts.
- **Reports & exports** — TXT (configurable line format), CSV, JSON and rich,
  sanitized HTML reports, generated in background workers.
- **Three themes** — Light, Dark, Midnight — switchable live and persisted.
- **CLI** for headless automation.

## Architecture

```
app/
├── core/          constants, enums, config, paths, logging, events, models
├── database/      SQLAlchemy models, engine, repository, filters, migrations
├── proxy/         parser, deduplicator, quality scoring
├── discovery/     base, manager, importer, normalizer, scheduler, providers/
├── testing/       validator, engine, profiles, anonymity, dns_analysis
├── intelligence/  base, manager, geoip, asn, isp, classification, providers/
├── monitoring/    (monitoring service lives in services/)
├── reports/       HTML/CSV/JSON/TXT report generator + templates
├── services/      jobs, pipeline, monitoring, exporters, credentials, bootstrap
├── workers/       Qt threads bridging async engines to the GUI
└── ui/            themes, main window, pages, widgets, dialogs, models
```

See [`docs/architecture.md`](docs/architecture.md) for the full design.

## Installation

Requires **Python 3.10+**.

```bash
git clone https://github.com/G33l0/ProxyAtlas.git
cd ProxyAtlas
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

On Linux you may also need Qt runtime libraries:
`sudo apt-get install libegl1 libgl1 libxkbcommon0 libfontconfig1`.

### Headless / CLI-only (servers, containers, Termux)

Environments without a Qt display use the headless requirements (no PyQt6):

```bash
pip install -r requirements-cli.txt
```

Everything except the GUI works: discovery, validation, intelligence,
classification, monitoring, exports and stats via `proxyatlas --help`.

## Running on Termux (Android)

ProxyAtlas runs headlessly on **Termux** — the full engine (discovery,
validation over HTTP/HTTPS/SOCKS4/SOCKS5, intelligence, classification, exports)
works from the command line. The PyQt6 GUI is desktop-only; on Termux you use
the CLI, which is fully featured.

```bash
# 1. Install Termux from F-Droid, then update and install build prerequisites
pkg update && pkg upgrade
pkg install python git rust clang openssl
# (Rust + OpenSSL are needed to build the 'cryptography' package.)

# 2. Get ProxyAtlas
git clone https://github.com/G33l0/ProxyAtlas.git
cd ProxyAtlas

# 3. Install the headless dependencies
pip install -r requirements-cli.txt

# 4. Use it
python run.py --help
python run.py --import proxies.txt          # import a list into the queue
python run.py --validate --profile quick    # validate the queue for real
python run.py --export working.txt --working-only
python run.py --stats
```

**Storing the database on shared storage / SD card (Termux):**

```bash
termux-setup-storage        # grant storage access (one time)
# Point ProxyAtlas at shared storage so the DB isn't in the app sandbox:
python run.py --stats       # creates config first
# then edit the database path, or from Python:
python - <<'PY'
from app.core.config import Settings
from app.core.paths import paths
s = Settings.load(paths.config_path)
s.set("database", "path", "/data/data/com.termux/files/home/storage/shared/ProxyAtlas")
s.save()
print("DB path set to shared storage")
PY
```

If a launch with no arguments (or `--gui`) is attempted on Termux, ProxyAtlas
detects that PyQt6 is unavailable and prints CLI usage instead of failing.

See [`docs/termux.md`](docs/termux.md) for troubleshooting.

## Running

```bash
python run.py            # launch the GUI
# or, if installed as a package:
proxyatlas               # GUI
proxyatlas --help        # CLI
```

First launch creates the data directory, database and default settings, runs
migrations, loads themes and providers, and shows the dashboard with an
onboarding hint.

## Testing

```bash
python -m pytest -q
```

The suite (unit, integration and UI) uses a local mock proxy server and never
requires a live external proxy service. UI tests run headless via Qt's
offscreen platform.

## Building

```bash
python build_release.py            # clean, validate, lint, test, build, package
python build_release.py --skip-build   # checks only
pyinstaller ProxyAtlas.spec        # build the executable directly
```

On Windows this produces `dist/ProxyAtlas/ProxyAtlas.exe` and a `release/`
folder. Icons, themes, migrations and report templates are bundled.

## Provider configuration

Configure discovery sources under **Sources**, and intelligence provider
credentials under **Settings → Providers**. API keys are **never** hard-coded
and **never** written to logs; proxy credentials are encrypted at rest. See
[`docs/providers.md`](docs/providers.md).

## Discovery configuration

See [`docs/discovery.md`](docs/discovery.md) for source types, formats and the
Internet Discovery module.

## Database

SQLite via SQLAlchemy with Alembic migrations. To keep large datasets off the
system disk, point **Settings → Database** at an external drive or custom folder
(with a one-click **Relocate now**); ProxyAtlas falls back to the default
location gracefully if the drive is unavailable at launch. Location and schema
are described in [`docs/database.md`](docs/database.md).

## Themes

Light, Dark and Midnight, defined centrally in `app/ui/theme.py`. Switch under
**Settings → Appearance** or the About/Settings pages; the choice persists.

## Plugin architecture

New discovery sources, intelligence providers and protocols can be added behind
the existing interfaces without touching the core. Drop a provider module in
`app/discovery/providers/future_providers/` and load it via the custom-provider
loader. See [`docs/development.md`](docs/development.md).

## Troubleshooting

- **Qt fails to start on Linux** — install the Qt runtime libraries listed above,
  or set `QT_QPA_PLATFORM=offscreen` for headless use.
- **No intelligence data** — check connectivity and Settings → Providers; the
  offline provider still supplies reverse-DNS/hosting hints.
- **Nothing validates as working** — confirm your validation endpoints under
  Settings → Testing are reachable from your network.
- **Logs** live in the data directory under `logs/` (`application.log`,
  `errors.log`, `jobs.log`, `discovery.log`). Credentials are redacted.

## License

MIT — see [LICENSE](LICENSE).
