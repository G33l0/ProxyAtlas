# Contributing to ProxyAtlas

Thanks for your interest in improving ProxyAtlas!

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Before submitting

- Run the linter: `ruff check app tests`
- Run the tests: `python -m pytest -q`
- Keep modules reasonably sized and use type hints and docstrings on public
  interfaces.
- Do not hard-code credentials or demonstration proxy records.
- Do not perform blocking network I/O on the Qt GUI thread — use the async
  engines and Qt workers.

## Adding a provider

- **Discovery provider**: implement `DiscoveryProvider` (see
  `app/discovery/base.py`) and register it, or drop a module in
  `app/discovery/providers/future_providers/` exposing `build(config)` or
  `PROVIDER`.
- **Intelligence provider**: implement `IntelligenceProvider` (see
  `app/intelligence/base.py`) and register it with the manager.

See `docs/development.md` for architecture details.

## Commit style

Write clear, imperative commit messages describing the change and its rationale.
