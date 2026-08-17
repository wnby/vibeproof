from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vibeproof.scanner import RepositoryScanner, ScanPolicy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vibeproof", description="Evidence-backed Python repository takeover")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="scan a local repository without executing its code")
    scan_parser.add_argument("path", type=Path, help="repository root")
    scan_parser.add_argument("--output", "-o", type=Path, help="write the JSON manifest to this path")
    scan_parser.add_argument("--max-files", type=int, default=5_000)
    scan_parser.add_argument("--max-file-size", type=int, default=1_000_000, help="maximum readable file size in bytes")

    serve_parser = subparsers.add_parser("serve", help="run the local FastAPI service")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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
    if args.command == "serve":
        import uvicorn

        uvicorn.run("vibeproof.api:app", host=args.host, port=args.port)
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


def _configure_stdout_utf8() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
