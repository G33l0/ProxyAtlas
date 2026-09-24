"""Import proxies from files or pasted text into candidates."""

from __future__ import annotations

from pathlib import Path

from app.core.enums import Protocol
from app.core.models import ProxyCandidate
from app.discovery.normalizer import normalize_csv, normalize_json, normalize_lines


class ProxyImporter:
    """Turn user-provided files/text into candidates (validation happens later)."""

    def import_file(
        self, path: str | Path, default_protocol: Protocol = Protocol.HTTP
    ) -> tuple[list[ProxyCandidate], list[tuple[str, str]]]:
        p = Path(path).expanduser()
        text = p.read_text(encoding="utf-8", errors="replace")
        source = f"import:{p.name}"
        suffix = p.suffix.lower()
        if suffix == ".json":
            return normalize_json(text, source, default_protocol)
        if suffix == ".csv":
            return normalize_csv(text, source, default_protocol)
        return normalize_lines(text.splitlines(), source, default_protocol, str(p))

    def import_text(
        self, text: str, source: str = "import:paste", default_protocol: Protocol = Protocol.HTTP
    ) -> tuple[list[ProxyCandidate], list[tuple[str, str]]]:
        return normalize_lines(text.splitlines(), source, default_protocol)
