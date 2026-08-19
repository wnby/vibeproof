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

## Day 4 runtime boundary

Runtime checks execute untrusted repository test code and may therefore read, write, start processes, or use the
network with the current operating-system user's permissions. Day 4 keeps this boundary visible and small:

- default to a typed plan; require explicit `--execute` to run it
- expose only `pytest` and `pytest --collect-only`, with tokenized arguments and `shell=False`
- select an explicit interpreter, the target `.venv`, or the current interpreter; never install dependencies
- run in the selected repository with a wall-clock timeout
- bound recorded stdout and stderr
- remove environment variables whose names look like tokens, secrets, passwords, API keys, credentials, or auth values
- compare deterministic repository snapshots before and after execution and never silently revert changes
- preserve non-zero exits, missing dependencies, timeouts, and launch errors as runtime evidence

This is not a sandbox. It does not isolate the network, operating-system credentials, child processes, CPU, or memory.
Use disposable environments for repositories that are not trusted enough to execute locally. Multi-user permissions,
policy DSLs, automatic dependency installation, container orchestration, and arbitrary shell access are intentionally
outside the Day 4 scope.

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
