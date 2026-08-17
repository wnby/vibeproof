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
