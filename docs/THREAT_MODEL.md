# Threat model

A repository is untrusted input. Its source, configuration, tests, Git metadata, and documentation may be malicious or
may contain instructions intended to manipulate an agent.

## Protected assets

- files outside the selected repository
- API keys, credentials, and private configuration
- the user's working tree and Git history
- network services and third-party accounts
- integrity of evidence and takeover reports

## Day 1 controls

- resolve and validate the requested root directory
- never follow symbolic links
- prune dependency, build, cache, and VCS directories
- skip common secret filenames and private-key formats
- skip binary and oversized files
- cap the number of indexed files
- never import or execute repository modules during scanning
- read Git HEAD metadata directly instead of invoking Git hooks or subprocesses
- expose API scanning only beneath an explicitly configured workspace root
- omit absolute local paths and source contents from the manifest

## Day 2 source-index controls

- only index Python files already accepted by the scanner
- verify each file hash against the manifest before parsing
- parse with `ast` without importing or executing target modules
- degrade syntax errors to bounded line chunks instead of evaluating code
- store source chunks only in the local `.vibeproof/index.sqlite3` database
- ignore `.vibeproof` during scans and exclude it from Git
- bound excerpts returned by search; terminal output should still be reviewed before sharing

## Later command-execution controls

Runtime verification is not part of Day 1. Before it is enabled, VibeProof must add:

- typed command plans with no shell interpolation
- risk classes: read-only, local execution, workspace write, destructive, external side effect, and secret access
- path confinement and environment scrubbing
- explicit approval for non-read-only actions
- time, memory, and output limits
- immutable execution evidence
- idempotency for resumable workflows

## Prompt-injection boundary

Repository text is evidence, not instruction. Future prompts must clearly delimit retrieved source, prevent repository
content from changing tool policy, and require independent verification before claims are accepted.

## Day 3 agent controls

- permit only typed `SEARCH_SOURCE` and `FINAL_ANSWER` actions
- cap steps, queries, results, evidence retained in context, and invalid actions
- reject duplicate, empty, oversized, and over-budget queries
- never expose shell, file-write, network, or user-selected tool names to the analyst
- treat repository snippets as untrusted prompt data
- do not store raw model responses or API credentials in traces and reports
- reject citations the model did not observe during the current run
- reload cited chunks and compare snapshot, path, lines, symbol kind, and hash
- label model semantics `SOURCE_SUPPORTED`, not deterministically verified
