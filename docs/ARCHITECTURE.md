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

## Planned agent workflow

```text
RepositoryManifest
-> RepositoryAnalystAgent
-> RuntimeVerifierAgent
-> TutorAgent
-> EvidenceReviewAgent
-> TakeoverCoordinator
-> TakeoverReport
```

Deterministic services own file access, indexing, and command execution. Agents reason over typed artifacts and cannot
bypass tool policy. The coordinator may only publish an accepted artifact after evidence review.
