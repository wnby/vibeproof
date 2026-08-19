# Day 6: source-grounded repository tutor

Day 6 extends the one-command takeover report with an ordered learning path, hands-on exercises, and quiz questions.
The feature is designed for a developer who can run an AI-generated repository but needs a concrete route to explain
and take ownership of it.

## One-command workflow

```bash
uv run python -m vibeproof takeover /path/to/repository \
  --provider mock --format markdown --output reports/takeover.md
```

The stage trace now contains:

```text
SCAN
INDEX
ANALYZE
LEARNING_PLAN
RUNTIME_PLAN or RUNTIME_EXECUTION
REPORT
```

Default takeover remains plan-only and does not execute target code.

## Learning evidence selection

`LearningEvidenceSelector` starts with the architecture report's accepted references and then adds bounded results for
entrypoints, tests, detected frameworks, and dependency files. The default budget is 12 chunks from at most eight
queries, with two results per query. Existing SQLite source evidence is reused; no embedding service or vector database
was introduced.

The tutor state includes bounded excerpts and stable metadata:

- chunk and snapshot IDs
- repository-relative path and line range
- symbol and symbol kind
- content hash
- bounded source excerpt

Repository text is explicitly treated as untrusted evidence rather than instructions.

## Tutor and review

`RepositoryTutorAgent` makes one structured model call and requests 3-5 ordered learning units plus questions. Each unit
contains an objective, rationale, hands-on exercise, and evidence IDs. Each question identifies its learning unit,
difficulty, evaluation points, and evidence IDs.

`LearningPlanReviewer` independently checks every item. It rejects citations that were not supplied to the tutor,
belong to another snapshot, are absent from the current index, or no longer match path, lines, symbol kind, and hash.
Questions referencing rejected units and duplicate unit/question identifiers are also rejected.

Statuses are:

- `SOURCE_GROUNDED`: units and questions passed citation review
- `DEGRADED`: some useful items survived but other items were rejected
- `FAILED`: no valid learning plan was produced

These statuses describe evidence provenance. They do not make a deterministic claim about the quality of a model's
teaching explanation.

## Provider behavior

- `mock` uses separate deterministic analyst and tutor clients for an offline reproducible workflow
- `openai-compatible` uses the configured chat-completions transport for both roles
- `ollama` uses the configured local model for both roles

The mock tutor builds a reading path from distinct source files and demonstrates orchestration and review. A configured
language model is still required for a genuinely semantic teaching narrative.

## Real validation

VibeProof generated four reviewed units and four questions covering its entrypoint, CLI, and tests. MindBridge generated
four reviewed units and four questions covering `app/harness/runner.py`, `app/main.py`,
`tests/test_event_driven_multi_agent.py`, and `tests/test_memory_compaction.py`. Both plan-only takeovers returned
`COMPLETED`, with learning status `SOURCE_GROUNDED` and runtime status `PLANNED`.

The complete local suite contains 75 passing tests, including invented citations, stale snapshots, invalid Tutor JSON,
bounded evidence loading, deterministic mock output, and coordinator integration.

## Deliberate limits

Day 6 generates questions but does not accept or score user answers. It does not persist student progress, add a chat
interface, install a vector database, or modify target code. Evidence-backed answer review is the next milestone.
