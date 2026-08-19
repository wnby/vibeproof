# Day 4: plan-first runtime verification

Day 4 adds runtime evidence without turning VibeProof into a general shell runner or a security platform. The
deterministic `RuntimeVerifier` answers one narrow question: what happened when a known Python test check ran in this
repository, with which interpreter and against which snapshot?

## User flow

Planning is the default and does not execute target code:

```bash
uv run python -m vibeproof verify /path/to/repository --check pytest
```

The JSON plan shows the fixed tokenized command, selected interpreter source, repository snapshot, timeout, and output
limit. Execution requires a separate flag:

```bash
uv run python -m vibeproof verify /path/to/repository --check pytest --execute
```

The only checks in the Day 4 catalog are:

- `pytest`: `python -m pytest -q`
- `pytest-collect`: `python -m pytest --collect-only -q`

There is no positional command, extra-argument escape hatch, shell interpolation, environment creation, or automatic
package installation.

## Evidence model

`CommandPlan` records intent before execution. `RuntimeEvidence` records the command status, exit code, duration,
bounded stdout/stderr, output truncation, and the number of removed environment variables. The enclosing
`RuntimeVerificationReport` compares repository snapshots and can report:

- `PLANNED`
- `PASSED`
- `FAILED`
- `TIMED_OUT`
- `EXECUTION_ERROR`
- `SNAPSHOT_CHANGED`

When tests pass but write a tracked/scannable file, command evidence remains `PASSED` while the report becomes
`SNAPSHOT_CHANGED`. This preserves both facts instead of overwriting one with the other.

## Interpreter selection

The verifier uses the first available option:

1. the path supplied by `--python`
2. `.venv/Scripts/python.exe` or `.venv/bin/python` inside the target
3. VibeProof's current `sys.executable`

The report identifies the source. A repository-local interpreter is rendered as a relative path so a public example
does not leak a developer's home directory.

## Real validation

VibeProof verified itself with its repository `.venv`: 59 tests passed, exit code 0, and the before/after snapshots
matched.

MindBridge's `pytest-collect` check produced a useful negative result. Its `.venv` existed, but that interpreter did not
contain `pytest`, so collection exited with code 1 and `No module named pytest`. The repository snapshot did not change.
VibeProof did not install anything or reinterpret an environment failure as a source-code failure.

## Deliberate limits

The verifier is not an operating-system sandbox. It does not block network access, constrain child-process trees, or
limit CPU and memory. Those controls belong in a disposable container or CI runner when the target repository is not
trusted. Day 4 keeps the portfolio project focused on evidence, explicit execution, and honest failure reporting.
