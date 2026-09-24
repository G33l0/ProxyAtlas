"""Professional HTML report generation.

Builds a self-contained, theme-styled HTML report with discovery/validation
summaries, classification/protocol/country breakdowns, latency and reliability
statistics, and a detailed results table. All dynamic content is HTML-escaped
to prevent injection from proxy/provider strings. Reports run in background
workers (see :mod:`app.workers`).
"""

from __future__ import annotations

import html
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.enums import ValidationStatus
from app.services.exporters import EXPORT_COLUMNS


def _bar_rows(counter: dict[str, int], total: int) -> str:
    if not counter:
        return '<div class="empty">No data</div>'
    rows = []
    top = max(counter.values()) or 1
    for label, count in sorted(counter.items(), key=lambda kv: kv[1], reverse=True):
        pct = (count / total * 100.0) if total else 0.0
        width = (count / top * 100.0)
        rows.append(
            f'<div class="bar-row"><span class="bar-label">{html.escape(str(label))}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{width:.1f}%"></span></span>'
            f'<span class="bar-value">{count} ({pct:.1f}%)</span></div>'
        )
    return "".join(rows)


def build_report_html(rows: list[dict[str, Any]], title: str = "ProxyAtlas Report") -> str:
    total = len(rows)
    working = [r for r in rows if r.get("status") == ValidationStatus.WORKING.value]
    failed = [r for r in rows if r.get("status") != ValidationStatus.WORKING.value]

    classifications = Counter(r.get("classification") or "unknown" for r in working)
    protocols = Counter(r.get("protocol") or "?" for r in rows)
    countries = Counter(r.get("country") or "Unknown" for r in working)

    latencies = [float(r["latency"]) for r in working if r.get("latency") is not None]
    reliabilities = [float(r["reliability"]) for r in working if r.get("reliability") is not None]

    def stat_block(values: list[float], unit: str) -> str:
        if not values:
            return '<span class="muted">n/a</span>'
        return (
            f"min {min(values):.0f}{unit} · "
            f"avg {statistics.mean(values):.0f}{unit} · "
            f"median {statistics.median(values):.0f}{unit} · "
            f"max {max(values):.0f}{unit}"
        )

    head = "".join(f"<th>{html.escape(c)}</th>" for c in EXPORT_COLUMNS)
    body = []
    for r in working[:1000]:
        cells = "".join(
            f"<td>{html.escape('' if r.get(c) is None else str(r.get(c)))}</td>"
            for c in EXPORT_COLUMNS
        )
        body.append(f"<tr>{cells}</tr>")

    generated = html.escape(datetime.now(timezone.utc).isoformat(timespec="seconds"))
    success_rate = (len(working) / total * 100.0) if total else 0.0

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#0b1220;--panel:#111c30;--border:#22314d;--text:#e2e8f0;--muted:#94a3b8;--accent:#38bdf8;--accent2:#22d3ee}}
*{{box-sizing:border-box}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--text);margin:0;padding:32px}}
h1{{color:var(--accent);margin:0 0 4px}} h2{{color:var(--accent2);margin-top:32px;border-bottom:1px solid var(--border);padding-bottom:6px}}
.meta{{color:var(--muted);margin-bottom:24px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px}}
.card{{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px}}
.card .num{{font-size:28px;font-weight:700;color:var(--accent)}} .card .lbl{{color:var(--muted);font-size:13px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}
.bar-row{{display:flex;align-items:center;gap:10px;margin:6px 0;font-size:13px}}
.bar-label{{width:130px;color:var(--muted)}} .bar-track{{flex:1;background:#0a1526;border-radius:6px;height:14px;overflow:hidden}}
.bar-fill{{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2))}}
.bar-value{{width:110px;text-align:right;color:var(--text)}}
table{{border-collapse:collapse;width:100%;font-size:12px;margin-top:12px}}
th,td{{border:1px solid var(--border);padding:5px 7px;text-align:left;white-space:nowrap}}
th{{background:#0e1a2e;color:#7dd3fc;position:sticky;top:0}} tr:nth-child(even){{background:#0d1728}}
.muted{{color:var(--muted)}} .empty{{color:var(--muted);font-style:italic}}
.wrap{{overflow:auto;max-height:640px;border:1px solid var(--border);border-radius:8px}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<div class="meta">Generated {generated}</div>

<div class="cards">
  <div class="card"><div class="num">{total}</div><div class="lbl">Total Proxies</div></div>
  <div class="card"><div class="num">{len(working)}</div><div class="lbl">Working</div></div>
  <div class="card"><div class="num">{len(failed)}</div><div class="lbl">Failed</div></div>
  <div class="card"><div class="num">{success_rate:.1f}%</div><div class="lbl">Success Rate</div></div>
  <div class="card"><div class="num">{(statistics.mean(latencies) if latencies else 0):.0f}ms</div><div class="lbl">Avg Latency</div></div>
</div>

<h2>Summary</h2>
<div class="grid2">
  <div class="card"><div class="lbl">Latency</div><div>{stat_block(latencies,'ms')}</div>
    <div class="lbl" style="margin-top:10px">Reliability</div><div>{stat_block(reliabilities,'%')}</div></div>
  <div class="card"><div class="lbl">Protocols</div>{_bar_rows(dict(protocols), total)}</div>
</div>

<h2>Classification Breakdown</h2>
<div class="card">{_bar_rows(dict(classifications), len(working))}</div>

<h2>Country Distribution (working)</h2>
<div class="card">{_bar_rows(dict(countries.most_common(15)), len(working))}</div>

<h2>Detailed Results (working, up to 1000)</h2>
<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{''.join(body) or '<tr><td colspan="99" class="empty">No working proxies</td></tr>'}</tbody></table></div>
</body></html>"""


def write_report(
    rows: list[dict[str, Any]], path: str | Path, fmt: str = "html", title: str = "ProxyAtlas Report"
) -> int:
    """Write a report in the requested format. Returns record count."""
    path = Path(path)
    fmt = fmt.lower()
    if fmt == "html":
        path.write_text(build_report_html(rows, title), encoding="utf-8")
        return len(rows)
    # For non-HTML report formats, delegate to exporters.
    from app.services.exporters import export_rows

    return export_rows(rows, path, fmt, working_only=False)
