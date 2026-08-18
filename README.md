# VibeProof

VibeProof is an evidence-backed onboarding and takeover agent for Python repositories. It helps a developer move from
"the project runs" to "I can explain, verify, and safely change it."

The current milestone scans a local repository without executing its code, builds a stable manifest, and creates a
local Python source index whose search results point to concrete files, symbols, and line ranges.

## Status

Implemented:

- uv-based Python 3.11 project and lockfile
- deterministic local repository scanner
- sensitive-file, binary-file, symlink, size, and file-count safeguards
- `RepositoryManifest`, `Evidence`, and `TakeoverReport` contracts
- read-only Git metadata parsing without executing repository hooks
- CLI and restricted FastAPI scan endpoint
- unit tests and GitHub Actions CI
- an example manifest generated from the MindBridge repository
- AST-based classes, functions, async functions, decorators, docstrings, and import extraction
- snapshot-bound semantic source chunks with stable IDs and line evidence
- a local SQLite evidence store that is excluded from Git
- deterministic source retrieval with bounded excerpts and content hashes
- a real MindBridge index validation covering 49 Python files and 489 symbols

Not implemented yet:

- LLM-generated architecture analysis
- source-grounded learning plans and quizzes
- command execution or code modification
- GitHub App integration
- fine-tuned tool-risk model

## Quick start

```bash
uv sync --group dev
uv run python -m vibeproof scan /path/to/python-repository
```

Build the local source evidence index:

```bash
uv run python -m vibeproof index /path/to/python-repository
```

Search by qualified symbol, path, import, decorator, or source phrase:

```bash
uv run python -m vibeproof search /path/to/python-repository "ChatService.stream_chat"
uv run python -m vibeproof search /path/to/python-repository "router.post" --json
```

By default, source contents are stored in `.vibeproof/index.sqlite3`. Use `--database` to select another local path.

Write a manifest to a file:

```bash
uv run python -m vibeproof scan /path/to/python-repository --output target/repository-manifest.json
```

Run the API:

```bash
# Set this to a directory containing repositories that the API may inspect.
export VIBEPROOF_WORKSPACE_ROOT=/path/to/repositories
uv run python -m vibeproof serve
```

On PowerShell:

```powershell
$env:VIBEPROOF_WORKSPACE_ROOT = 'D:\repositories'
uv run python -m vibeproof serve
```

The API deliberately accepts paths relative to `VIBEPROOF_WORKSPACE_ROOT`:

```http
POST /api/v1/repositories/scan
Content-Type: application/json

{"relativePath":"my-python-project"}
```

## Development

```bash
uv run ruff check .
uv run python -m pytest
```

## Safety boundary

Scanning and indexing do not import target modules, install dependencies, run tests, execute Git commands, follow
symlinks, or read common secret files. The indexer verifies scanned file hashes before parsing and keeps source contents
in an ignored local database. Repository execution will be introduced later behind an explicit approval and audit layer.
See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## Roadmap

1. ~~Source chunks with file and line evidence~~
2. Evidence-backed architecture analysis
3. Learning plans and source-grounded quizzes
4. Approved runtime verification and tool-risk policy
5. Repository takeover report and replayable traces

See [docs/MVP.md](docs/MVP.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/DAY2.md](docs/DAY2.md) for the
v0.1 scope and implementation notes.
