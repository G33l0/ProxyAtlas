# Changelog

All notable changes to ProxyAtlas are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
Semantic Versioning.

## [Unreleased]

### Added
- External-drive / custom database storage: point the database at any folder or
  drive (Settings → Database), with a one-click relocate, writability validation
  and graceful fallback to the default location when the drive is unavailable.

### Verified
- Real end-to-end run against a live public proxy feed (2,847 candidates →
  validated → genuine working proxies with exit IP, geolocation, ISP,
  classification, score and export).
- Internet Discovery generates candidates that enter the same validation
  pipeline with stored provenance.

## [1.0.0] - 2026-09-24

### Added
- Initial release of ProxyAtlas.
- Modular discovery engine with file, feed, API, custom/plugin and Internet
  Discovery providers, all feeding a single validation pipeline.
- Asynchronous validation engine for HTTP/HTTPS/SOCKS4/SOCKS5 with real
  proxy-mediated requests, exit-IP detection, latency, reliability, anonymity
  and DNS analysis; Quick/Standard/Deep and custom profiles.
- Controlled concurrency with pause/resume/stop and live statistics.
- IP intelligence (ip-api.com, ipinfo.io, offline reverse-DNS/hosting) with a
  pluggable provider manager.
- Evidence-based classification (Residential, Mobile, Datacenter, ISP, Business,
  Educational, Government, Unknown) and explainable quality scoring.
- Persistent SQLite database (SQLAlchemy + Alembic) with identity-based
  deduplication, advanced filtering, saved filters and collections.
- Professional PyQt6 UI: dashboard, discovery, internet discovery, proxies,
  testing, monitoring, collections, reports, sources, settings and about pages.
- Three themes (Light, Dark, Midnight), original branding and icons.
- Monitoring with history charts; TXT/CSV/JSON exports and HTML reports.
- Global job manager, rotating logs with credential redaction, encrypted
  credential storage.
- CLI for headless automation and a PyInstaller build pipeline.
- Unit, integration and UI test suites.
