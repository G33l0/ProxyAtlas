# Development

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

## Project layout

See [architecture.md](architecture.md). Engine code (core, database, proxy,
discovery, testing, intelligence, services) is Qt-free and unit-testable; the
`ui/` and `workers/` layers depend on PyQt6.

## Conventions

- Type hints on public functions; docstrings on public interfaces.
- Structured exceptions from `app/core/exceptions.py`.
- No blocking network/DB work on the Qt GUI thread - use the async engines and
  Qt workers.
- No hard-coded credentials or demonstration proxy records.
- Keep modules focused and reasonably sized.

## Adding a discovery provider

1. Subclass `DiscoveryProvider`, implement `discover()` as an async generator
   yielding `ProxyCandidate`, and declare `config_schema()` for the UI.
2. Register via `DiscoveryManager.register_provider("mykey", MyProvider)`, or
   drop a plugin module in `app/discovery/providers/future_providers/` exposing
   `build(config)` or a `PROVIDER` class.

## Adding an intelligence provider

1. Subclass `IntelligenceProvider`, implement async `lookup(ip)`.
2. Register with `IntelligenceManager.register(provider)`. Higher priority
   (lower number) runs first; non-empty fields win, later providers fill gaps.

## Adding a protocol

Extend `Protocol` in `app/core/enums.py`, teach the parser any new scheme
aliases, and add a transport branch in `app/testing/validator.py`.

## Testing

```bash
python -m pytest -q          # unit + integration + UI
ruff check app tests         # lint
```

Tests use a local mock proxy/origin server (see `tests/conftest.py`) and never
require live external services. UI tests run under Qt's offscreen platform.

## Building a release

```bash
python build_release.py
```

Cleans previous builds, validates dependencies, regenerates assets, lints, runs
tests, builds the PyInstaller executable and assembles `release/`.
