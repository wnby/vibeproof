"""通过 Python AST 构建快照绑定的源码结构索引。

本模块在重新核对文件哈希后解析类、函数、异步函数、装饰器、文档字符串和导入关系，并生成带稳定
ID、行号与内容哈希的源码分块；它只解析文本，不导入或执行目标模块。
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from vibeproof.schemas import (
    ImportEdge,
    RepositoryManifest,
    SourceChunk,
    SourceSymbol,
    SymbolKind,
)


@dataclass(frozen=True)
class IndexPolicy:
    max_chunk_lines: int = 120
    overlap_lines: int = 12

    def __post_init__(self) -> None:
        if self.max_chunk_lines < 1:
            raise ValueError("max_chunk_lines must be positive")
        if self.overlap_lines < 0:
            raise ValueError("overlap_lines cannot be negative")
        if self.overlap_lines >= self.max_chunk_lines:
            raise ValueError("overlap_lines must be smaller than max_chunk_lines")


@dataclass(frozen=True)
class IndexedSource:
    symbols: tuple[SourceSymbol, ...]
    chunks: tuple[SourceChunk, ...]
    imports: tuple[ImportEdge, ...]
    indexed_files: int
    warnings: tuple[str, ...]


class PythonSourceIndexer:
    """Build deterministic source artifacts without importing target modules."""

    def __init__(self, policy: IndexPolicy | None = None):
        self.policy = policy or IndexPolicy()

    def build(self, root: str | Path, manifest: RepositoryManifest) -> IndexedSource:
        repository_root = Path(root).expanduser().resolve(strict=True)
        if not repository_root.is_dir():
            raise NotADirectoryError(f"repository root is not a directory: {repository_root}")

        symbols: list[SourceSymbol] = []
        chunks: list[SourceChunk] = []
        imports: list[ImportEdge] = []
        warnings: list[str] = []
        indexed_files = 0

        python_records = sorted(
            (record for record in manifest.files if record.language == "Python"),
            key=lambda record: record.path,
        )
        for record in python_records:
            path = repository_root / Path(record.path)
            try:
                if path.is_symlink():
                    warnings.append(f"skipped symlinked source: {record.path}")
                    continue
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(repository_root):
                    warnings.append(f"skipped source outside repository: {record.path}")
                    continue
                data = resolved.read_bytes()
            except OSError:
                warnings.append(f"source became unreadable after scanning: {record.path}")
                continue

            if hashlib.sha256(data).hexdigest() != record.sha256:
                warnings.append(f"source changed after manifest scan: {record.path}")
                continue
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                warnings.append(f"source is not UTF-8: {record.path}")
                continue

            file_symbols, file_imports, syntax_warning = _parse_python(
                text=text,
                path=record.path,
                snapshot_id=manifest.snapshot_id,
            )
            symbols.extend(file_symbols)
            imports.extend(file_imports)
            if syntax_warning:
                warnings.append(syntax_warning)
            chunks.extend(
                _build_chunks(
                    text=text,
                    path=record.path,
                    snapshot_id=manifest.snapshot_id,
                    symbols=file_symbols,
                    policy=self.policy,
                    parsed=syntax_warning is None,
                )
            )
            indexed_files += 1

        return IndexedSource(
            symbols=tuple(sorted(symbols, key=lambda item: (item.path, item.start_line, item.qualified_name))),
            chunks=tuple(sorted(chunks, key=lambda item: (item.path, item.start_line, item.chunk_id))),
            imports=tuple(sorted(imports, key=lambda item: (item.source_path, item.line, item.module))),
            indexed_files=indexed_files,
            warnings=tuple(warnings),
        )


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self, path: str, snapshot_id: str):
        self.path = path
        self.snapshot_id = snapshot_id
        self.parents: list[tuple[str, SymbolKind]] = []
        self.symbols: list[SourceSymbol] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._record(node, SymbolKind.CLASS)
        self.parents.append((node.name, SymbolKind.CLASS))
        self.generic_visit(node)
        self.parents.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        kind = SymbolKind.METHOD if self._directly_inside_class() else SymbolKind.FUNCTION
        self._record(node, kind)
        self.parents.append((node.name, kind))
        self.generic_visit(node)
        self.parents.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        kind = SymbolKind.ASYNC_METHOD if self._directly_inside_class() else SymbolKind.ASYNC_FUNCTION
        self._record(node, kind)
        self.parents.append((node.name, kind))
        self.generic_visit(node)
        self.parents.pop()

    def _directly_inside_class(self) -> bool:
        return bool(self.parents and self.parents[-1][1] == SymbolKind.CLASS)

    def _record(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, kind: SymbolKind) -> None:
        qualified_name = ".".join([*(name for name, _ in self.parents), node.name])
        start_line = min((decorator.lineno for decorator in node.decorator_list), default=node.lineno)
        end_line = getattr(node, "end_lineno", node.lineno)
        signature = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                signature = f"{node.name}({ast.unparse(node.args)})"
            except (AttributeError, ValueError):
                signature = node.name
        decorators: list[str] = []
        for decorator in node.decorator_list:
            try:
                decorators.append(ast.unparse(decorator))
            except (AttributeError, ValueError):
                continue
        symbol_id = _stable_id(
            "symbol",
            self.snapshot_id,
            self.path,
            qualified_name,
            str(start_line),
            str(end_line),
        )
        self.symbols.append(
            SourceSymbol(
                symbol_id=symbol_id,
                snapshot_id=self.snapshot_id,
                path=self.path,
                module=_module_name(self.path),
                qualified_name=qualified_name,
                kind=kind,
                start_line=start_line,
                end_line=end_line,
                signature=signature,
                docstring=_clean_docstring(ast.get_docstring(node, clean=True)),
                decorators=decorators,
                parent_name=".".join(name for name, _ in self.parents) or None,
            )
        )


def _parse_python(
    text: str,
    path: str,
    snapshot_id: str,
) -> tuple[list[SourceSymbol], list[ImportEdge], str | None]:
    try:
        tree = ast.parse(text, filename=path)
    except (SyntaxError, ValueError) as exc:
        line = getattr(exc, "lineno", None)
        suffix = f" at line {line}" if line else ""
        return [], [], f"AST parsing failed for {path}{suffix}; used line chunks"

    visitor = _SymbolVisitor(path=path, snapshot_id=snapshot_id)
    visitor.visit(tree)
    imports: list[ImportEdge] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(
                    ImportEdge(
                        snapshot_id=snapshot_id,
                        source_path=path,
                        module=alias.name,
                        alias=alias.asname,
                        line=node.lineno,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(
                    ImportEdge(
                        snapshot_id=snapshot_id,
                        source_path=path,
                        module=module,
                        imported_name=alias.name,
                        alias=alias.asname,
                        level=node.level,
                        line=node.lineno,
                    )
                )
    return visitor.symbols, imports, None


def _build_chunks(
    text: str,
    path: str,
    snapshot_id: str,
    symbols: list[SourceSymbol],
    policy: IndexPolicy,
    parsed: bool,
) -> list[SourceChunk]:
    lines = text.splitlines()
    if not lines:
        return []

    regions: list[tuple[int, int, str | None, SymbolKind]] = []
    if parsed:
        regions.append((1, len(lines), None, SymbolKind.MODULE))
        for symbol in symbols:
            regions.append((symbol.start_line, symbol.end_line, symbol.qualified_name, symbol.kind))
    else:
        regions.append((1, len(lines), None, SymbolKind.MODULE))

    chunks: list[SourceChunk] = []
    seen: set[tuple[int, int, str | None]] = set()
    for region_start, region_end, symbol, symbol_kind in regions:
        safe_end = min(region_end, len(lines))
        for start, end in _line_windows(region_start, safe_end, policy):
            key = (start, end, symbol)
            if key in seen:
                continue
            seen.add(key)
            content = "\n".join(lines[start - 1 : end]).strip("\n")
            if not content.strip():
                continue
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            chunks.append(
                SourceChunk(
                    chunk_id=_stable_id(
                        "chunk",
                        snapshot_id,
                        path,
                        symbol or "<module>",
                        str(start),
                        str(end),
                        content_hash,
                    ),
                    snapshot_id=snapshot_id,
                    path=path,
                    start_line=start,
                    end_line=end,
                    content_hash=content_hash,
                    content=content,
                    symbol=symbol,
                    symbol_kind=symbol_kind,
                )
            )
    return chunks


def _line_windows(start: int, end: int, policy: IndexPolicy) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    cursor = start
    step = policy.max_chunk_lines - policy.overlap_lines
    while cursor <= end:
        window_end = min(cursor + policy.max_chunk_lines - 1, end)
        windows.append((cursor, window_end))
        if window_end == end:
            break
        cursor += step
    return windows


def query_terms(query: str) -> tuple[str, ...]:
    raw_terms = re.findall(r"[A-Za-z_][A-Za-z0-9_\.]*|\d+|[\u3400-\u9fff]+", query.lower())
    expanded: list[str] = []
    for term in raw_terms:
        expanded.append(term)
        expanded.extend(part for part in re.split(r"[_\.]", term) if part and part != term)
    return tuple(dict.fromkeys(expanded))


def _clean_docstring(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.split())[:500]


def _module_name(path: str) -> str:
    parts = list(Path(path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return f"{prefix}:sha256:{digest.hexdigest()}"
