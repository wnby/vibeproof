# Day 2: source evidence indexing

Day 2 turns the Day 1 repository inventory into a local, line-addressable evidence index. The implementation remains
deterministic and does not call a model or execute target code.

## Delivered workflow

```text
RepositoryScanner
      |
      v
RepositoryManifest + snapshot_id
      |
      v
PythonSourceIndexer (AST only)
      |-------------------|
      v                   v
SourceSymbol/Chunk     ImportEdge
      |                   |
      +---------+---------+
                v
       local SQLite EvidenceStore
                |
                v
      ranked EvidenceHit results
```

## Index guarantees

- Only Python files accepted by the Day 1 scanner are considered.
- A file is hashed again before indexing; changed files are rejected instead of being attached to a stale snapshot.
- Parsing uses the standard-library `ast` module and never imports the target module.
- Syntax errors degrade to bounded line chunks and produce warnings.
- Stable chunk and symbol IDs include the repository snapshot, relative path, line range, and content hash.
- Decorator lines are included in symbol ranges, so route queries such as `router.post` lead to the decorated function.
- Source contents stay in a local ignored SQLite database. They are not added to `RepositoryManifest`.

## Deterministic retrieval

Search scores exact qualified-symbol matches first, followed by partial symbol, path, exact phrase, and individual term
matches. Each result includes a relative path, start/end lines, symbol kind, bounded excerpt, and content hash.

This retrieval is intentionally transparent. A future analyst agent can use it as a grounding tool before the project
adds embeddings or model-generated queries.

## MindBridge validation

The real repository produced:

- 49 indexed Python files
- 489 source symbols
- 575 source chunks
- 520 import edges
- zero warnings

Queries for `stream_chat`, `AgentHarness`, `EventDrivenAgentRuntimeService`, and `redis` all returned the expected source
file and symbol as the top result. The metadata-only record is committed at
`examples/mindbridge-index-summary.json`; the SQLite database and source excerpts remain local.
