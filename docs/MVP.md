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
-> scan structure and metadata
-> index source with file/line evidence
-> verify runtime facts with approved tools
-> generate a staged learning plan
-> ask source-grounded questions
-> review the user's answers against evidence
-> export a Repository Takeover Report
```

## v0.1 success criteria

- Supports local Python repositories.
- Never treats an unverified claim as verified.
- Every accepted architecture claim links to source or command evidence.
- Repository code is not executed during scanning.
- Commands require an explicit policy decision and auditable approval.
- A user can reproduce the demo without MySQL, Redis, or a paid model API.

## Core contracts

### RepositoryManifest

A stable snapshot of repository structure, languages, likely frameworks, entry points, tests, documentation, and Git
metadata. It deliberately excludes absolute local paths and file contents.

### Evidence

A source or runtime fact supporting a claim. Source evidence contains repository-relative path and line boundaries;
runtime evidence contains an approved command, exit code, and bounded output excerpt.

### TakeoverReport

The final handoff document containing verified claims, unresolved questions, learning progress, runtime checks, and
known limitations for one repository snapshot.

## Out of scope for v0.1

- autonomous code edits
- automatic bug repair
- arbitrary shell access
- remote execution
- multi-language semantic analysis
- multi-user authorization
- a production GitHub App
- QLoRA training
