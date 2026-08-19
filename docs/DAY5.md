# Day 5: unified repository takeover

Day 5 turns the previous four milestones into one user-facing workflow. A user supplies one local Python repository
path; `TakeoverCoordinator` scans it, replaces the snapshot-bound source index, runs the analyst and citation reviewer,
creates or executes a fixed runtime check, and composes a single report.

## Golden path

```bash
uv run python -m vibeproof takeover /path/to/repository --provider mock
```

The default is intentionally plan-only. The workflow may read and index source, but it does not run target code until
the operator adds `--execute`:

```bash
uv run python -m vibeproof takeover /path/to/repository \
  --provider mock --check pytest --execute \
  --format markdown --output reports/takeover.md
```

The earlier `scan`, `index`, `search`, `analyze`, and `verify` commands remain available for inspecting one stage.

## Workflow artifacts

```text
SCAN              RepositorySummary
INDEX             SourceIndexSummary + SQLite evidence
ANALYZE           ArchitectureReport + citation review
RUNTIME_PLAN      CommandPlan (default)
RUNTIME_EXECUTION RuntimeEvidence (--execute only)
REPORT            TakeoverReport
```

Every stage produces a `TakeoverStep` with its stage, status, duration, summary, and optional error. The final JSON or
Markdown report keeps the repository snapshot, technology overview, index counts, accepted/rejected claims, citations,
runtime result, unresolved questions, warnings, and workflow trace together.

## Honest partial completion

The status describes the whole takeover rather than merely whether the process returned:

- `COMPLETED`: scan, index, analyst, citation review, and runtime plan/pass completed
- `PARTIAL`: architecture or runtime evidence failed, but earlier artifacts remain useful
- `FAILED`: scanning or indexing failed, so grounded analysis could not proceed
- `SNAPSHOT_CHANGED`: runtime execution changed the scannable repository content

Model endpoint failures become a failed `ANALYZE` step while runtime planning continues. Non-zero test exits retain the
command, exit code, and bounded output. No stage installs dependencies or attempts an automatic repair.

## Real validation

VibeProof took over itself in one command:

- scanned 45 readable files
- indexed 25 Python files, 251 symbols, 312 chunks, and 255 imports
- accepted five source-grounded mock-provider claims and rejected zero
- executed the repository `.venv` test command
- passed 66 tests with exit code 0
- matched before and after snapshots
- returned `COMPLETED`

MindBridge's plan-only takeover:

- scanned 89 readable files
- indexed 49 Python files, 489 symbols, 575 chunks, and 520 imports
- accepted five source-grounded claims and rejected zero
- selected its `.venv` and planned `pytest --collect-only`
- returned `COMPLETED` without executing target code

An explicit MindBridge execution preserved the known environment failure: its `.venv` did not contain `pytest`, so
the runtime step exited with code 1, the report returned `PARTIAL`, and the repository snapshot remained unchanged.

## Deliberate limits

The coordinator is orchestration, not another Agent persona. It does not clone remote repositories, create environments,
install dependencies, start infrastructure, edit code, or accept arbitrary commands. Learning plans and source-grounded
quizzes remain the next milestone.
