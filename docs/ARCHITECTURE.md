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

## Planned agent workflow

```text
RepositoryManifest
-> Source evidence index
-> RepositoryAnalystAgent
-> RuntimeVerifierAgent
-> TutorAgent
-> EvidenceReviewAgent
-> TakeoverCoordinator
-> TakeoverReport
```

Deterministic services own file access, indexing, and command execution. Agents reason over typed artifacts and cannot
bypass tool policy. The coordinator may only publish an accepted artifact after evidence review.
