# VibeProof v0.1 MVP

## Problem

AI-assisted development can produce a repository that runs while its owner cannot explain its architecture, failure
paths, or change impact. VibeProof turns repository takeover into a stateful, evidence-backed workflow.

## Primary user

A Python developer, student, or incoming maintainer who needs to understand an unfamiliar or heavily AI-generated
repository before changing it.

## Golden path

```text
select local repository
-> run one coordinated scan/index/analyze/runtime-plan workflow
-> export an evidence-backed Repository Takeover Report
-> generate a staged learning plan
-> ask source-grounded questions
-> review the user's answers against evidence
```

## v0.1 success criteria

- Supports local Python repositories.
- Never treats an unverified claim as verified.
- Every accepted architecture claim links to source or command evidence.
- Repository code is not executed during scanning.
- Runtime checks require an explicit `--execute` decision and produce auditable command evidence.
- A user can reproduce the demo without MySQL, Redis, or a paid model API.

## Core contracts

### RepositoryManifest

A stable snapshot of repository structure, languages, likely frameworks, entry points, tests, documentation, and Git
metadata. It deliberately excludes absolute local paths and file contents.

### Evidence

A source or runtime fact supporting a claim. Source evidence contains repository-relative path and line boundaries;
runtime evidence contains an approved command, exit code, and bounded output excerpt.

### TakeoverReport

The current handoff document contains repository metadata, index statistics, source-supported claims, rejected claims,
unresolved questions, reviewed learning units, source-grounded quiz questions, runtime plans or evidence, workflow
steps, and known limitations for one repository snapshot. A snapshot-bound answer template and evidence-backed review
report close the learning loop and summarize weak units and progress.

## Out of scope for v0.1

- autonomous code edits
- automatic bug repair
- arbitrary shell access
- remote execution
- multi-language semantic analysis
- multi-user authorization
- a production GitHub App
- QLoRA training
