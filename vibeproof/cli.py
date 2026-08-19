from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from vibeproof.analyst import AnalystPolicy, RepositoryAnalystAgent
from vibeproof.evidence_store import EvidenceStore, IndexNotFoundError
from vibeproof.model_client import ModelClientError, create_model_client
from vibeproof.reporting import render_architecture_report
from vibeproof.scanner import RepositoryScanner, ScanPolicy
from vibeproof.schemas import EvidenceHit
from vibeproof.source_index import IndexPolicy, PythonSourceIndexer

DEFAULT_DATABASE = Path(".vibeproof/index.sqlite3")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vibeproof", description="Evidence-backed Python repository takeover")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="scan a local repository without executing its code")
    scan_parser.add_argument("path", type=Path, help="repository root")
    scan_parser.add_argument("--output", "-o", type=Path, help="write the JSON manifest to this path")
    scan_parser.add_argument("--max-files", type=int, default=5_000)
    scan_parser.add_argument("--max-file-size", type=int, default=1_000_000, help="maximum readable file size in bytes")

    index_parser = subparsers.add_parser("index", help="build a local evidence index for a Python repository")
    index_parser.add_argument("path", type=Path, help="repository root")
    index_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="local SQLite index path")
    index_parser.add_argument("--max-files", type=int, default=5_000)
    index_parser.add_argument("--max-file-size", type=int, default=1_000_000)
    index_parser.add_argument("--max-chunk-lines", type=int, default=120)
    index_parser.add_argument("--overlap-lines", type=int, default=12)

    search_parser = subparsers.add_parser("search", help="search an indexed repository for source evidence")
    search_parser.add_argument("path", type=Path, help="repository root")
    search_parser.add_argument("query", help="symbol, path, import, or source text to find")
    search_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="local SQLite index path")
    search_parser.add_argument("--limit", type=int, default=5)
    search_parser.add_argument("--max-files", type=int, default=5_000)
    search_parser.add_argument("--max-file-size", type=int, default=1_000_000)
    search_parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    analyze_parser = subparsers.add_parser("analyze", help="run the evidence-grounded repository analyst agent")
    analyze_parser.add_argument("path", type=Path, help="repository root")
    analyze_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="local SQLite index path")
    analyze_parser.add_argument(
        "--provider",
        choices=("mock", "openai-compatible", "ollama"),
        default=os.getenv("VIBEPROOF_AI_PROVIDER", "mock"),
    )
    analyze_parser.add_argument("--model", default=None, help="model name; may also use VIBEPROOF_AI_MODEL")
    analyze_parser.add_argument("--base-url", default=None, help="model endpoint; may also use VIBEPROOF_AI_BASE_URL")
    analyze_parser.add_argument("--max-steps", type=int, default=8)
    analyze_parser.add_argument("--max-queries", type=int, default=5)
    analyze_parser.add_argument("--search-limit", type=int, default=3)
    analyze_parser.add_argument("--max-files", type=int, default=5_000)
    analyze_parser.add_argument("--max-file-size", type=int, default=1_000_000)
    analyze_parser.add_argument("--format", choices=("json", "markdown"), default="json")
    analyze_parser.add_argument("--output", "-o", type=Path, help="write the report instead of printing it")

    serve_parser = subparsers.add_parser("serve", help="run the local FastAPI service")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            scanner = RepositoryScanner(ScanPolicy(max_files=args.max_files, max_file_size_bytes=args.max_file_size))
            manifest = scanner.scan(args.path)
            rendered = manifest.model_dump_json(indent=2, by_alias=True)
            if args.output:
                output = args.output.expanduser().resolve()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(rendered + "\n", encoding="utf-8")
            else:
                _configure_stdout_utf8()
                print(rendered)
            return 0
        if args.command == "index":
            scan_policy = ScanPolicy(max_files=args.max_files, max_file_size_bytes=args.max_file_size)
            manifest = RepositoryScanner(scan_policy).scan(args.path)
            index_policy = IndexPolicy(max_chunk_lines=args.max_chunk_lines, overlap_lines=args.overlap_lines)
            indexed = PythonSourceIndexer(index_policy).build(args.path, manifest)
            summary = EvidenceStore(args.database).replace_snapshot(
                repository_name=manifest.repository_name,
                snapshot_id=manifest.snapshot_id,
                indexed=indexed,
            )
            _configure_stdout_utf8()
            print(summary.model_dump_json(indent=2))
            return 0
        if args.command == "search":
            scan_policy = ScanPolicy(max_files=args.max_files, max_file_size_bytes=args.max_file_size)
            manifest = RepositoryScanner(scan_policy).scan(args.path)
            hits = EvidenceStore(args.database).search(
                snapshot_id=manifest.snapshot_id,
                query=args.query,
                limit=args.limit,
            )
            _configure_stdout_utf8()
            if args.json:
                print(json.dumps([hit.model_dump(mode="json") for hit in hits], ensure_ascii=False, indent=2))
            else:
                _print_hits(hits)
            return 0
        if args.command == "analyze":
            scan_policy = ScanPolicy(max_files=args.max_files, max_file_size_bytes=args.max_file_size)
            manifest = RepositoryScanner(scan_policy).scan(args.path)
            model = create_model_client(provider=args.provider, model=args.model, base_url=args.base_url)
            analyst_policy = AnalystPolicy(
                max_steps=args.max_steps,
                max_queries=args.max_queries,
                search_limit=args.search_limit,
            )
            report = RepositoryAnalystAgent(
                store=EvidenceStore(args.database),
                model=model,
                policy=analyst_policy,
            ).run(manifest)
            rendered = report.model_dump_json(indent=2) if args.format == "json" else render_architecture_report(report)
            if args.output:
                output = args.output.expanduser().resolve()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(rendered.rstrip() + "\n", encoding="utf-8")
            else:
                _configure_stdout_utf8()
                print(rendered.rstrip())
            return 0 if report.run_status.value == "COMPLETED" else 1
        if args.command == "serve":
            import uvicorn

            uvicorn.run("vibeproof.api:app", host=args.host, port=args.port)
            return 0
    except (IndexNotFoundError, ModelClientError, NotADirectoryError, OSError, PermissionError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.error(f"unknown command: {args.command}")
    return 2


def _configure_stdout_utf8() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


def _print_hits(hits: list[EvidenceHit]) -> None:
    if not hits:
        print("No source evidence matched the query.")
        return
    for index, hit in enumerate(hits, start=1):
        symbol = f" [{hit.symbol}]" if hit.symbol else ""
        print(f"{index}. {hit.path}:{hit.start_line}-{hit.end_line}{symbol} score={hit.score:.2f}")
        for line in hit.excerpt.splitlines():
            print(f"   {line}")
        print()


if __name__ == "__main__":
    raise SystemExit(main())
