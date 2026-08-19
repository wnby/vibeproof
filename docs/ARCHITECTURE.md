# Architecture

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

## Planned agent workflow

```text
RepositoryManifest
-> Source evidence index
-> RepositoryAnalystAgent
-> RuntimeVerifier
-> TutorAgent
-> EvidenceReviewAgent
-> TakeoverCoordinator
-> TakeoverReport
```

Deterministic services own file access, indexing, and command execution. Agents reason over typed artifacts and cannot
bypass tool policy. The coordinator may only publish an accepted artifact after evidence review.
