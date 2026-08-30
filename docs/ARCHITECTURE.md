# Architecture

## Current package boundaries

```text
interfaces (CLI / API / Web)
        |
        v
workflows --------> agents
   |                 |  |
   v                 v  v
runtime          repository <----> llm
   |                 |             |
   +-----------------+-------------+
                     v
                core/models
```

- `config.py` is the only environment-configuration source.
- `core/models/` contains pure typed contracts and imports no application services.
- `repository/`, `llm/`, and `runtime/` provide bounded capabilities.
- `agents/` reason through the model protocol and repository evidence; they do not know about HTTP or CLI concerns.
- `workflows/` coordinate complete user use cases without becoming another reasoning Agent.
- `interfaces/` translate user input into workflow calls, while `reports/` only render typed results.
- `tests/test_architecture.py` enforces the allowed import direction with Python AST inspection.

The structure uses Strategy for model providers, Decorator for bounded retry, Repository for evidence persistence, and a
Coordinator/Facade for the complete takeover workflow. These patterns are kept local; there is no generic framework or
dependency-injection container.

## Day 1

```text
CLI or restricted FastAPI endpoint
              |
              v
      RepositoryScanner
       /      |       \
path policy  file scan  safe Git metadata reader
       \      |       /
              v
      RepositoryManifest
```

The scanner is deterministic. It does not use an LLM and does not execute target code.

## Day 2

```text
RepositoryManifest
       |
       v
PythonSourceIndexer -- ast.parse only
   /          |          \
symbols    chunks      imports
   \          |          /
       EvidenceStore (local SQLite)
                |
                v
     ranked file/line EvidenceHit
```

The indexer verifies every file against the manifest hash before reading it. Source text is stored only in an ignored
local database and is never added to the shareable manifest. Search is deterministic and returns bounded excerpts with
repository-relative paths, line ranges, symbol kinds, and content hashes.

## Day 3

```text
Manifest + EvidenceStore
          |
          v
RepositoryAnalystAgent <---- ModelClient
     | SEARCH_SOURCE
     v
EvidenceStore.search
     | EvidenceHit
     v
FINAL_ANSWER
     |
     v
CitationReviewer ---> ArchitectureReport + AgentTraceStep
```

The model chooses when and what to search, but the runtime owns every capability. Only two typed actions exist. Final
citations must have been observed in this run and are reloaded from the current SQLite snapshot before acceptance.
Model-authored claims are labeled `SOURCE_SUPPORTED`; citation validation is not presented as semantic proof.

## Day 4

```text
repository + fixed check
          |
          v
   RuntimeVerifier.plan
   /       |        \
snapshot  Python   tokenized argv
          |
     default: PLANNED
          |
    explicit --execute
          v
 subprocess (shell=False, timeout, bounded output)
          |
          v
 RuntimeEvidence + post-run snapshot
          |
          v
 RuntimeVerificationReport
```

Runtime verification is a deterministic service, not another model loop. Its command catalog contains only `pytest`
and `pytest --collect-only`. Plans select an explicit interpreter, a target `.venv`, or the current process in that
order. Execution never creates an environment or installs dependencies. A changed post-run snapshot is reported as
`SNAPSHOT_CHANGED`; VibeProof records the change but does not revert user files.

## Day 5

```text
local repository path
         |
         v
 TakeoverCoordinator
   | SCAN ------> RepositorySummary
   | INDEX -----> SourceIndexSummary + EvidenceStore
   | ANALYZE ---> ArchitectureReport + citation review
   | RUNTIME ---> plan by default, evidence with --execute
   | REPORT
         v
 TakeoverReport + TakeoverStep trace
```

The coordinator composes existing deterministic services and the bounded analyst; it does not add a second reasoning
loop. Scan or index failure creates a `FAILED` report because later evidence cannot be grounded. Analyst and runtime
failures create a `PARTIAL` report while preserving completed artifacts. A changed runtime snapshot becomes
`SNAPSHOT_CHANGED`. The `takeover` CLI is the user-facing golden path, while the earlier commands remain useful for
debugging individual stages.

## Day 6

```text
Manifest + ArchitectureReport + EvidenceStore
                    |
                    v
          LearningEvidenceSelector
 architecture refs + entrypoints + tests + frameworks
                    |
            bounded EvidenceHit set
                    v
          RepositoryTutorAgent <---- task-specific ModelClient
                    |
             LearningPlanDraft
                    v
          LearningPlanReviewer
 observed + persisted + current snapshot checks
                    |
                    v
     LearningPlan (units + exercises + quiz + references)
```

The selector deterministically gathers at most a bounded number of source chunks; the tutor cannot cite other IDs.
The reviewer reloads requested references from SQLite and rejects unseen, stale, missing, or metadata-mismatched
citations. `SOURCE_GROUNDED` describes provenance, not proof that a model-authored teaching explanation is semantically
perfect. A failed learning stage makes the unified takeover `PARTIAL` while runtime planning still proceeds.

## Current and planned workflow

```text
Repository path
-> TakeoverCoordinator
   -> RepositoryManifest
   -> Source evidence index
   -> RepositoryAnalystAgent + CitationReviewer
   -> RepositoryTutorAgent + LearningPlanReviewer
   -> RuntimeVerifier
-> TakeoverReport
-> QuizSubmission template
-> AnswerReviewAgent + evidence integrity review
-> AnswerReviewReport + LearningProgress
```

Deterministic services own file access, indexing, and command execution. Agents reason over typed artifacts and cannot
bypass tool policy. The coordinator reports incomplete stages instead of treating partial output as a completed run.

## Day 7

```text
TakeoverReport + QuizSubmission + EvidenceStore
                    |
             identity checks
     report + plan + snapshot + question IDs
                    |
                    v
            AnswerReviewAgent <---- review ModelClient
       question + rubric + answer + bounded excerpts
                    |
          AnswerAssessmentDraft
                    v
     question/evidence/score contract review
                    |
                    v
      AnswerReviewReport + LearningProgress
```

The answer reviewer never receives a source-search or execution capability. It can assess only the source excerpts
already bound to the current question. The runtime derives pass/fail state from a validated score and rejects invented
citations. The mock provider is explicitly structure-only and never emits a semantic score.

## Persistent Web runs

```text
Web page -> POST /api/v1/runs -> WebRunService -> background TakeoverCoordinator
              |                     |                    |
              v                     v                    v
         immediate run_id      RunStore JSON      real TakeoverStep callback
              |                     ^                    |
              +---- polling --------+--------------------+
```

Each Run owns one JSON record under `.vibeproof/runs`; SQLite continues to own source evidence only. This separation
keeps persistence explicit: the report, stage checkpoints, configuration and learning attempts are portable JSON,
while bounded source text remains in the evidence index. The Web process needs no queue service for this local-first
release. A Tutor or Runtime retry reloads the saved report, verifies that the repository snapshot is unchanged, and
reuses the accepted Analyst artifact.
