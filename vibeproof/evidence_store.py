from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vibeproof.schemas import EvidenceHit, ImportEdge, SourceChunk, SourceIndexSummary, SourceSymbol, SymbolKind
from vibeproof.source_index import IndexedSource, query_terms


class IndexNotFoundError(LookupError):
    pass


class EvidenceStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).expanduser().resolve()

    def replace_snapshot(
        self,
        repository_name: str,
        snapshot_id: str,
        indexed: IndexedSource,
    ) -> SourceIndexSummary:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            _create_schema(connection)
            connection.execute("BEGIN")
            for table in ("chunks", "symbols", "imports", "snapshots"):
                connection.execute(f"DELETE FROM {table} WHERE snapshot_id = ?", (snapshot_id,))
            connection.execute(
                """
                INSERT INTO snapshots (
                    snapshot_id, repository_name, indexed_files, symbol_count, chunk_count, import_count
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    repository_name,
                    indexed.indexed_files,
                    len(indexed.symbols),
                    len(indexed.chunks),
                    len(indexed.imports),
                ),
            )
            connection.executemany(
                """
                INSERT INTO symbols (
                    symbol_id, snapshot_id, path, module, qualified_name, kind, start_line, end_line,
                    signature, docstring, decorators_json, parent_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_symbol_row(symbol) for symbol in indexed.symbols],
            )
            connection.executemany(
                """
                INSERT INTO chunks (
                    chunk_id, snapshot_id, path, start_line, end_line, content_hash,
                    content, symbol, symbol_kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_chunk_row(chunk) for chunk in indexed.chunks],
            )
            connection.executemany(
                """
                INSERT INTO imports (
                    snapshot_id, source_path, module, imported_name, alias, level, line
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [_import_row(edge) for edge in indexed.imports],
            )
        return SourceIndexSummary(
            repository_name=repository_name,
            snapshot_id=snapshot_id,
            indexed_files=indexed.indexed_files,
            symbol_count=len(indexed.symbols),
            chunk_count=len(indexed.chunks),
            import_count=len(indexed.imports),
            database_path=self.database_path.as_posix(),
            warnings=list(indexed.warnings),
        )

    def search(self, snapshot_id: str, query: str, limit: int = 5) -> list[EvidenceHit]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        normalized_query = query.strip().lower()
        if not normalized_query:
            raise ValueError("query cannot be empty")
        terms = query_terms(query)
        if not terms:
            raise ValueError("query must contain a searchable term")
        if not self.database_path.is_file():
            raise IndexNotFoundError("source index does not exist; run `vibeproof index` first")

        with self._connect() as connection:
            _create_schema(connection)
            snapshot = connection.execute(
                "SELECT 1 FROM snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            if snapshot is None:
                raise IndexNotFoundError("this repository snapshot is not indexed; run `vibeproof index` again")
            rows = connection.execute(
                """
                SELECT chunk_id, snapshot_id, path, start_line, end_line, content_hash,
                       content, symbol, symbol_kind
                FROM chunks
                WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            ).fetchall()

        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            score = _score_row(row, normalized_query, terms)
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], item[1]["path"], item[1]["start_line"], item[1]["chunk_id"]))

        return [
            EvidenceHit(
                chunk_id=row["chunk_id"],
                snapshot_id=row["snapshot_id"],
                path=row["path"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                symbol=row["symbol"],
                symbol_kind=SymbolKind(row["symbol_kind"]),
                score=round(score, 4),
                content_hash=row["content_hash"],
                excerpt=_excerpt(row["content"], terms),
            )
            for score, row in scored[:limit]
        ]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            snapshot_id TEXT PRIMARY KEY,
            repository_name TEXT NOT NULL,
            indexed_files INTEGER NOT NULL,
            symbol_count INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL,
            import_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS symbols (
            symbol_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            module TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            kind TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            signature TEXT,
            docstring TEXT,
            decorators_json TEXT NOT NULL,
            parent_name TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_symbols_snapshot ON symbols(snapshot_id);
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            content TEXT NOT NULL,
            symbol TEXT,
            symbol_kind TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_snapshot ON chunks(snapshot_id);
        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
            source_path TEXT NOT NULL,
            module TEXT NOT NULL,
            imported_name TEXT,
            alias TEXT,
            level INTEGER NOT NULL,
            line INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_imports_snapshot ON imports(snapshot_id);
        """
    )


def _symbol_row(symbol: SourceSymbol) -> tuple[object, ...]:
    return (
        symbol.symbol_id,
        symbol.snapshot_id,
        symbol.path,
        symbol.module,
        symbol.qualified_name,
        symbol.kind.value,
        symbol.start_line,
        symbol.end_line,
        symbol.signature,
        symbol.docstring,
        json.dumps(symbol.decorators, ensure_ascii=False),
        symbol.parent_name,
    )


def _chunk_row(chunk: SourceChunk) -> tuple[object, ...]:
    return (
        chunk.chunk_id,
        chunk.snapshot_id,
        chunk.path,
        chunk.start_line,
        chunk.end_line,
        chunk.content_hash,
        chunk.content,
        chunk.symbol,
        chunk.symbol_kind.value,
    )


def _import_row(edge: ImportEdge) -> tuple[object, ...]:
    return (
        edge.snapshot_id,
        edge.source_path,
        edge.module,
        edge.imported_name,
        edge.alias,
        edge.level,
        edge.line,
    )


def _score_row(row: sqlite3.Row, query: str, terms: tuple[str, ...]) -> float:
    symbol = (row["symbol"] or "").lower()
    path = row["path"].lower()
    content = row["content"].lower()
    score = 0.0
    if symbol == query:
        score += 100.0
    elif query in symbol:
        score += 60.0
    if query in path:
        score += 35.0
    if query in content:
        score += 20.0
        if symbol:
            score += 25.0
    for term in terms:
        if term == symbol:
            score += 30.0
        elif term in symbol:
            score += 15.0
        if term in path:
            score += 8.0
        score += min(content.count(term), 5) * 1.5
    return score


def _excerpt(content: str, terms: tuple[str, ...], max_characters: int = 500) -> str:
    collapsed = "\n".join(line.rstrip() for line in content.splitlines()).strip()
    lowered = collapsed.lower()
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - max_characters // 3)
    end = min(len(collapsed), start + max_characters)
    excerpt = collapsed[start:end]
    if start:
        excerpt = "…" + excerpt
    if end < len(collapsed):
        excerpt += "…"
    return excerpt
