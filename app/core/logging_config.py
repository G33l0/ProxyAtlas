"""Rotating logs (application/errors/jobs/discovery) plus console. RedactionFilter
strips passwords, tokens and user:pass@ before anything hits disk.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False

# Patterns that redact secrets from any log record's rendered message.
_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(://[^/\s:@]+):([^/\s@]+)@"), r"\1:***@"),  # user:pass@host
    (re.compile(r"((?:password|passwd|pwd|secret|token|api[_-]?key|authorization)\s*[=:]\s*)\S+",
                re.IGNORECASE), r"\1***"),
]


class RedactionFilter(logging.Filter):
    """Redact credentials from log messages before they are emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = msg
        for pattern, repl in _REDACTIONS:
            redacted = pattern.sub(repl, redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def _make_handler(path: Path, level: int, max_bytes: int, backups: int,
                  fmt: logging.Formatter) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(fmt)
    handler.addFilter(RedactionFilter())
    return handler


def configure_logging(
    logs_dir: Path,
    level: str = "INFO",
    max_bytes: int = 2_000_000,
    backup_count: int = 5,
) -> None:
    """Configure root logging with rotating files. Safe to call once."""
    global _CONFIGURED
    logs_dir.mkdir(parents=True, exist_ok=True)
    numeric = getattr(logging, str(level).upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(numeric)
    # Clear existing handlers (e.g. on reconfigure / test reruns).
    for h in list(root.handlers):
        root.removeHandler(h)

    root.addHandler(_make_handler(logs_dir / "application.log", numeric, max_bytes, backup_count, fmt))

    err = _make_handler(logs_dir / "errors.log", logging.ERROR, max_bytes, backup_count, fmt)
    root.addHandler(err)

    console = logging.StreamHandler()
    console.setLevel(numeric)
    console.setFormatter(fmt)
    console.addFilter(RedactionFilter())
    root.addHandler(console)

    # Dedicated channels for jobs and discovery.
    _configure_channel("proxyatlas.jobs", logs_dir / "jobs.log", numeric, max_bytes, backup_count, fmt)
    _configure_channel("proxyatlas.discovery", logs_dir / "discovery.log", numeric, max_bytes, backup_count, fmt)

    # Quiet noisy third-party loggers.
    for noisy in ("httpx", "httpcore", "asyncio", "aiohttp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def _configure_channel(name: str, path: Path, level: int, max_bytes: int,
                       backups: int, fmt: logging.Formatter) -> None:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.addHandler(_make_handler(path, level, max_bytes, backups, fmt))
    # Also propagate to root so console/application.log see it.
    logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def jobs_logger() -> logging.Logger:
    return logging.getLogger("proxyatlas.jobs")


def discovery_logger() -> logging.Logger:
    return logging.getLogger("proxyatlas.discovery")
