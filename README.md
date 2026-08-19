# VibeProof

VibeProof is an evidence-backed onboarding and takeover agent for Python repositories. It helps a developer move from
"the project runs" to "I can explain, verify, and safely change it."

The current milestone accepts one local repository path and coordinates scanning, source indexing, evidence-grounded
architecture analysis, citation review, and plan-first runtime verification into one takeover report.

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
- a bounded `RepositoryAnalystAgent` with `SEARCH_SOURCE` and `FINAL_ANSWER` actions
- citation integrity review against the current SQLite snapshot
- auditable Agent traces and JSON/Markdown architecture reports
- offline mock, OpenAI-compatible, and Ollama model providers
- plan-first runtime verification with fixed `pytest` and `pytest --collect-only` checks
- target-interpreter discovery, timeouts, bounded output, environment scrubbing, and before/after snapshots
- JSON and Markdown runtime reports that preserve both passing and failing evidence
- a `TakeoverCoordinator` that preserves partial results when analysis or runtime checks fail
- one-command JSON/Markdown takeover reports with a stage-by-stage execution trace

Not implemented yet:

- LLM-generated architecture analysis
- source-grounded learning plans and quizzes
- arbitrary command execution or code modification
- GitHub App integration
- fine-tuned tool-risk model

## Quick start

```bash
uv sync --group dev
uv run python -m vibeproof takeover /path/to/python-repository --provider mock
```

Write the complete plan-only report as Markdown:

```bash
uv run python -m vibeproof takeover /path/to/python-repository \
  --provider mock --format markdown --output reports/takeover.md
```

Explicitly execute the fixed test check as part of takeover:

```bash
uv run python -m vibeproof takeover /path/to/python-repository \
  --provider mock --check pytest --execute
```

Without `--execute`, the unified workflow scans, indexes, analyzes, reviews citations, and creates a runtime plan but
does not run target code. A model or test failure produces a `PARTIAL` report instead of discarding earlier evidence.

The individual commands remain available for inspection and debugging:

```bash
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

Run the offline, reproducible analyst loop:

```bash
uv run python -m vibeproof analyze /path/to/python-repository --provider mock
```

Write a Markdown report:

```bash
uv run python -m vibeproof analyze /path/to/python-repository \
  --provider mock --format markdown --output reports/architecture.md
```

Use a local Ollama model after setting its name:

```bash
export VIBEPROOF_AI_MODEL=your-local-model
uv run python -m vibeproof analyze /path/to/python-repository --provider ollama
```

For an OpenAI-compatible endpoint, configure `VIBEPROOF_AI_MODEL`, `VIBEPROOF_AI_BASE_URL`, and optionally
`VIBEPROOF_AI_API_KEY`; keys are never accepted as CLI arguments.

Review a runtime plan without executing repository code:

```bash
uv run python -m vibeproof verify /path/to/python-repository --check pytest
```

Execute the fixed check only after reviewing the plan:

```bash
uv run python -m vibeproof verify /path/to/python-repository --check pytest --execute
uv run python -m vibeproof verify /path/to/python-repository --check pytest-collect --execute \
  --format markdown --output reports/runtime.md
```

Interpreter selection is explicit `--python`, then the target repository's `.venv`, then VibeProof's current Python.
VibeProof does not create environments, install missing packages, accept arbitrary command strings, or revert files.

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
symlinks, or read common secret files. Runtime verification is a separate, explicit `--execute` path. It uses tokenized
arguments with no shell, a timeout, bounded output, basic credential-looking environment removal, and repository
snapshots before and after execution. It is an evidence recorder, not a process sandbox. See
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

The analyst additionally limits its action, step, query, and evidence budgets. Repository snippets are untrusted prompt
data, and every final citation is independently reloaded from the current index. `SOURCE_SUPPORTED` means provenance was
validated; it does not claim that model-authored semantics were deterministically proven.

## Roadmap

1. ~~Source chunks with file and line evidence~~
2. ~~Evidence-backed architecture analysis~~
3. ~~Plan-first runtime verification and command evidence~~
4. ~~Repository takeover report and replayable workflow trace~~
5. Learning plans and source-grounded quizzes

See [docs/MVP.md](docs/MVP.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DAY2.md](docs/DAY2.md),
[docs/DAY3.md](docs/DAY3.md), [docs/DAY4.md](docs/DAY4.md), and [docs/DAY5.md](docs/DAY5.md).
