# Day 3: evidence-grounded repository analyst

Day 3 introduces VibeProof's first bounded agent loop. `RepositoryAnalystAgent` may ask for source searches and then
submit a final architecture report. It cannot execute target code, select arbitrary tools, or publish unobserved
citations.

## Agent loop

```text
RepositoryManifest + current source index
                  |
                  v
        RepositoryAnalystAgent
          |              ^
 SEARCH_SOURCE action    | EvidenceHit
          |              |
          v              |
       EvidenceStore -----
          |
          v
     FINAL_ANSWER action
          |
          v
      CitationReviewer
          |
          v
    ArchitectureReport + trace
```

The model receives bounded manifest metadata and previously observed evidence. Each turn must be one strict JSON
`SEARCH_SOURCE` or `FINAL_ANSWER` action. The loop enforces step, query, result, invalid-action, and evidence budgets.

## Citation integrity

The reviewer reloads every requested chunk from SQLite and checks:

- the model observed that chunk during this run
- the chunk belongs to the current repository snapshot
- the stored path, line range, symbol kind, and content hash match the observed result
- a claim has at least one valid citation
- duplicate claims and invented chunk IDs do not enter accepted output

Accepted model claims receive `SOURCE_SUPPORTED`, not `VERIFIED_FACT`. Valid citations establish provenance, but a
semantic architecture inference can still be wrong. `VERIFIED_FACT` is reserved for future deterministic fact
extractors.

## Provider boundary

- `mock` is an offline deterministic loop demonstration. It emits source-location claims, not a semantic narrative.
- `openai-compatible` uses a configured `/chat/completions` endpoint and reads its key only from
  `VIBEPROOF_AI_API_KEY`.
- `ollama` uses `/api/chat` with non-streaming JSON output.

No API key is accepted as a CLI argument, written into a report, or added to the agent trace.

## Prompt-injection boundary

Repository excerpts are explicitly labeled untrusted data. More importantly, enforcement does not depend on the model
following that instruction: Pydantic validates the action enum, the runtime exposes only source search, duplicate or
oversized searches are rejected, raw model output is not persisted, and final citations are independently reloaded.

## MindBridge offline validation

The deterministic provider completed four steps:

1. searched `app/harness/runner.py`
2. searched `app/main.py`
3. searched `app/mcp_tools/server.py`
4. submitted `FINAL_ANSWER`

The final report accepted five source-location claims, rejected zero, referenced five persisted chunks, and completed
with a verified citation-integrity status. A real semantic narrative remains an explicit unresolved question until a
language model is configured.
