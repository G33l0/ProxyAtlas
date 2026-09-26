# Running ProxyAtlas on Termux (Android)

ProxyAtlas runs **headlessly** on Termux. The processing engine — discovery,
validation over HTTP/HTTPS/SOCKS4/SOCKS5, exit-IP detection, intelligence,
classification, quality scoring, monitoring, exports and reports — is pure
Python and works from the command line. The PyQt6 desktop GUI is not available
on Termux (Qt6 has no Termux wheels), so you drive ProxyAtlas with the CLI,
which exposes the full workflow.

## Install

```bash
pkg update && pkg upgrade
pkg install python git rust clang openssl
git clone https://github.com/G33l0/ProxyAtlas.git
cd ProxyAtlas
pip install -r requirements-cli.txt
```

Notes:
- `rust`, `clang` and `openssl` are required to build the `cryptography`
  package. If the build fails, try `pkg install python-cryptography` to use the
  Termux-prebuilt version, then re-run the pip install.
- `geoip2` (offline GeoIP) is optional; remove it from `requirements-cli.txt` if
  you don't need offline geolocation.

## Usage

```bash
python run.py --version
python run.py --import proxies.txt            # import TXT/CSV/JSON into the queue
python run.py --discover                       # run all enabled sources (feeds/APIs)
python run.py --validate --profile quick       # real proxied validation
python run.py --export working.txt --working-only
python run.py --export working.csv --format csv
python run.py --stats
```

The CLI is the same engine the desktop app uses; results persist to the same
SQLite database, so you can validate on Termux and later open the database on a
desktop.

## Storing the database on shared storage / SD card

By default the database lives under Termux's private home
(`~/.local/share/ProxyAtlas`). To keep it on shared storage or an SD card
(useful for large datasets — the same "external drive" feature the desktop
Settings expose):

```bash
termux-setup-storage     # grant Android storage permission (one time)
```

Then set a custom database path (any of these works):

```bash
# Option A: environment variable for the whole data directory
export PROXYATLAS_DATA_DIR=~/storage/shared/ProxyAtlas
python run.py --stats

# Option B: persist a custom database path in config
python - <<'PY'
from app.core.config import Settings
from app.core.paths import paths
s = Settings.load(paths.config_path)
s.set("database", "path", "/storage/emulated/0/ProxyAtlas")  # or an SD card path
s.save()
PY
```

If the configured path is unavailable at launch (e.g. the SD card is not
mounted), ProxyAtlas falls back to the default location and logs a warning
rather than failing.

## Scheduling on Termux

Use `termux-job-scheduler` or `cron` (from `pkg install cronie`) to run periodic
validation, e.g. revalidate and re-export every few hours:

```bash
# crontab -e
0 */3 * * * cd ~/ProxyAtlas && python run.py --discover && python run.py --validate --profile quick && python run.py --export ~/storage/shared/working.txt --working-only
```

## Troubleshooting

- **`No module named PyQt6` when running with no arguments** — expected on
  Termux; ProxyAtlas prints CLI usage. Always pass a CLI flag.
- **`cryptography` build errors** — install `rust`, `clang`, `openssl`, or use
  `pkg install python-cryptography`.
- **`aiohttp` build errors** — ensure `clang` is installed; `pip install
  --upgrade pip` then retry.
- **Permission denied writing the database** — run `termux-setup-storage` and
  use a path under `~/storage/`.
