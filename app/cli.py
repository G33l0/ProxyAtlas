"""ProxyAtlas command-line interface.

The GUI is the primary interface; this CLI supports headless automation:

    proxyatlas --version
    proxyatlas --import file.txt
    proxyatlas --discover
    proxyatlas --validate [--profile quick] [--limit 500]
    proxyatlas --export results.csv [--format csv] [--working-only]
    proxyatlas --stats
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app import __version__
from app.database import repository as repo
from app.database.filters import FilterSpec
from app.services.app_context import AppContext
from app.services.bootstrap import bootstrap


def _cmd_import(ctx: AppContext, path: str) -> int:
    from app.discovery.importer import ProxyImporter

    candidates, errors = ProxyImporter().import_file(path)
    new = 0
    with ctx.database.session() as session:
        for cand in candidates:
            _, is_new = repo.add_discovery_candidate(session, cand, ctx.cipher)
            new += int(is_new)
    print(f"Imported {new} new candidate(s) from {path} ({len(errors)} skipped).")
    return 0


def _cmd_discover(ctx: AppContext) -> int:
    async def run() -> int:
        total_new = 0
        with ctx.database.session() as session:
            sources = [s for s in repo.list_sources(session) if s.enabled]
        if not sources:
            print("No enabled discovery sources configured.")
            return 0
        import json

        for src in sources:
            provider = ctx.discovery.build(src.provider, json.loads(src.config_json or "{}"))
            outcome = await ctx.discovery.run(provider)
            with ctx.database.session() as session:
                for cand in outcome.candidates:
                    _, is_new = repo.add_discovery_candidate(session, cand, ctx.cipher)
                    total_new += int(is_new)
            print(f"  {src.name}: {len(outcome.candidates)} found")
        print(f"Discovery complete: {total_new} new candidate(s) queued.")
        return 0

    return asyncio.run(run())


def _cmd_validate(ctx: AppContext, profile: str, limit: int | None) -> int:
    from app.services.pipeline import ProcessingPipeline
    from app.testing.profiles import get_profile

    async def run() -> int:
        with ctx.database.session() as session:
            rows = repo.list_discovery_results(session, limit=limit)
            candidates = [repo.discovery_result_to_candidate(r, ctx.cipher) for r in rows]
            ids = [r.id for r in rows]
        if not candidates:
            print("Discovery queue is empty. Import or discover first.")
            return 0
        pipeline = ProcessingPipeline(
            ctx.database, ctx.cipher, ctx.intelligence, ctx.testing_settings(),
            intelligence_enabled=ctx.intelligence_enabled(),
        )
        prof = get_profile(profile, ctx.custom_profiles())
        print(f"Validating {len(candidates)} candidate(s) with profile '{profile}'…")
        result = await pipeline.process(candidates, prof)
        with ctx.database.session() as session:
            repo.delete_discovery_results(session, ids)
        print(f"Done: {result.working} working, {result.failed} failed, {result.persisted} stored.")
        return 0

    return asyncio.run(run())


def _cmd_export(ctx: AppContext, path: str, fmt: str | None, working_only: bool) -> int:
    from app.services.exporters import export_rows, proxy_to_row

    fmt = fmt or path.rsplit(".", 1)[-1].lower()
    spec = FilterSpec()
    if working_only:
        spec.add("status", "eq", "working")
    with ctx.database.session() as session:
        rows = [proxy_to_row(p) for p in repo.query_proxies(session, spec, limit=1_000_000)]
        count = export_rows(rows, path, fmt, working_only=working_only)
        repo.record_export(session, fmt, path, count, None)
    print(f"Exported {count} prox{'y' if count == 1 else 'ies'} to {path} ({fmt}).")
    return 0


def _cmd_stats(ctx: AppContext) -> int:
    with ctx.database.session() as session:
        stats = repo.dashboard_stats(session)
        queue = len(repo.list_discovery_results(session))
    print("ProxyAtlas statistics")
    print(f"  Total proxies : {stats['total']}")
    print(f"  Working       : {stats['working']}")
    print(f"  Avg latency   : {stats['avg_latency']} ms")
    print(f"  Queue pending : {queue}")
    print("  By classification:")
    for cls, count in sorted(stats["by_classification"].items(), key=lambda kv: -kv[1]):
        if count:
            print(f"    {cls:12} {count}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="proxyatlas", description="ProxyAtlas — Discover. Validate. Analyze. Manage.")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    parser.add_argument("--import", dest="import_path", metavar="FILE", help="Import a proxy list into the queue")
    parser.add_argument("--discover", action="store_true", help="Run all enabled discovery sources")
    parser.add_argument("--validate", action="store_true", help="Validate the discovery queue")
    parser.add_argument("--export", dest="export_path", metavar="FILE", help="Export proxies to a file")
    parser.add_argument("--stats", action="store_true", help="Print database statistics")
    parser.add_argument("--profile", default="standard", help="Validation profile (quick/standard/deep)")
    parser.add_argument("--format", dest="fmt", help="Export format (txt/csv/json/html)")
    parser.add_argument("--limit", type=int, help="Limit number of candidates to validate")
    parser.add_argument("--working-only", action="store_true", help="Export only working proxies")
    parser.add_argument("--gui", action="store_true", help="Launch the graphical interface")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"ProxyAtlas {__version__}")
        return 0

    if args.gui or (argv is None and len(sys.argv) == 1):
        from app.main import main as gui_main

        return gui_main()

    ctx = bootstrap()

    if args.import_path:
        return _cmd_import(ctx, args.import_path)
    if args.discover:
        return _cmd_discover(ctx)
    if args.validate:
        return _cmd_validate(ctx, args.profile, args.limit)
    if args.export_path:
        return _cmd_export(ctx, args.export_path, args.fmt, args.working_only)
    if args.stats:
        return _cmd_stats(ctx)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
