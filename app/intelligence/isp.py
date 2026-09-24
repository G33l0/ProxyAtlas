"""ISP / organization normalization helpers."""

from __future__ import annotations


def clean_org(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    # Strip a leading "AS12345 " prefix that some sources prepend.
    parts = text.split(" ", 1)
    if parts[0].upper().startswith("AS") and parts[0][2:].isdigit() and len(parts) > 1:
        return parts[1].strip()
    return text or None


def prefer(*values: str | None) -> str | None:
    for v in values:
        if v:
            return v
    return None
