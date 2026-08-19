# Day 7: evidence-backed answer review

Day 7 closes the first learning loop. A takeover report can now become an editable answer file, and submitted answers
can be reviewed against the exact source snapshot and question evidence that produced the quiz.

## End-to-end workflow

Generate a JSON takeover report and its local SQLite evidence index:

```bash
uv run python -m vibeproof takeover /path/to/repository \
  --provider mock --format json --output reports/takeover.json
```

Create an answer template:

```bash
uv run python -m vibeproof quiz reports/takeover.json \
  --output reports/answers.json
```

Fill each `answer` field, then review it:

```bash
uv run python -m vibeproof review reports/takeover.json reports/answers.json \
  --database .vibeproof/index.sqlite3 --provider ollama --model your-model \
  --format markdown --output reports/review.md
```

The review command is read-only with respect to the target repository. It reads the report, answer file, and local
evidence index; it does not execute or modify target code.

## Identity and evidence checks

Before a model sees an answer, VibeProof verifies:

- `report_id`, `plan_id`, and `snapshot_id` agree across the report and submission
- every submitted question ID exists and appears only once
- every question citation is present in the report and current SQLite snapshot
- path, line range, symbol, symbol kind, snapshot, and content hash still match

For each answered question, only that question's bounded source excerpts are supplied. The model cannot successfully
cite evidence belonging to another question. A wrong question ID, missing score, invented citation, malformed JSON, or
model error becomes a `REJECTED` assessment rather than a fabricated grade.

## Honest offline behavior

The `mock` reviewer intentionally performs structure-only review. It confirms that an answer was supplied and that the
source citations are available, but returns no score and uses `STRUCTURE_ONLY` / `NOT_ASSESSED`. This keeps the offline
demo deterministic without pretending that string length or keyword overlap proves understanding.

Use an OpenAI-compatible endpoint or Ollama for semantic assessment. Scores at or above the configurable passing
threshold become `ANSWERED`; lower scores become `NEEDS_IMPROVEMENT`. Model statuses are not trusted directly—the
runtime derives status from the validated score.

## Progress report

JSON and Markdown reports include:

- answered versus total questions
- semantically assessed and passed questions
- incomplete, weak, and rejected answers
- completion and evidence-backed mastery percentages
- weak learning units and recommended units to revisit
- per-answer feedback, strengths, gaps, and file/line citations

Progress is a report artifact, not a user database. Re-running review creates a new report and does not silently merge
prior attempts.

## Verification

The suite contains 89 tests. Day 7 coverage includes report/submission identity mismatches, duplicate and unknown
questions, blank answers, structure-only mock behavior, score thresholds, invented model citations, malformed files,
Markdown output, and the full `takeover -> quiz -> review` CLI path.

## Deliberate limits

Day 7 does not add a web UI, accounts, cross-attempt persistence, vector search, fine-tuning, arbitrary command
execution, dependency installation, or target-code modification. Those are post-MVP choices rather than hidden parts of
the learning loop.
