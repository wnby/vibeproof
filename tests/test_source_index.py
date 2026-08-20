"""验证 Python AST 源码索引的结构抽取和完整性保护。

测试覆盖类、同步与异步函数、方法、签名、装饰器、导入关系、稳定分块，以及扫描后文件被修改或语法
无效时的处理，确认索引过程不会执行目标代码。
"""

from pathlib import Path

from vibeproof.scanner import RepositoryScanner
from vibeproof.schemas import SymbolKind
from vibeproof.source_index import IndexPolicy, PythonSourceIndexer

DEMO_SOURCE = '''import asyncio
from demo.tools import Tool as ToolAlias

@registered("greeter")
class Greeter:
    """Create a greeting."""

    @classmethod
    async def greet(cls, name: str) -> str:
        """Return a friendly greeting."""

        def normalize(value: str) -> str:
            return value.strip()

        return f"Hello {normalize(name)}"


def top_level(value: int = 1) -> int:
    return value + 1
'''


def _build_repository(root: Path, source: str = DEMO_SOURCE) -> None:
    package = root / "demo"
    package.mkdir()
    (package / "service.py").write_text(source, encoding="utf-8")


def test_ast_indexer_extracts_symbols_decorators_and_imports(tmp_path: Path) -> None:
    _build_repository(tmp_path)
    manifest = RepositoryScanner().scan(tmp_path)

    indexed = PythonSourceIndexer().build(tmp_path, manifest)
    by_name = {symbol.qualified_name: symbol for symbol in indexed.symbols}

    assert by_name["Greeter"].kind == SymbolKind.CLASS
    assert by_name["Greeter"].module == "demo.service"
    assert by_name["Greeter"].decorators == ["registered('greeter')"]
    assert by_name["Greeter.greet"].kind == SymbolKind.ASYNC_METHOD
    assert by_name["Greeter.greet"].decorators == ["classmethod"]
    assert by_name["Greeter.greet"].signature == "greet(cls, name: str)"
    assert by_name["Greeter.greet"].docstring == "Return a friendly greeting."
    assert by_name["Greeter.greet.normalize"].kind == SymbolKind.FUNCTION
    assert by_name["top_level"].kind == SymbolKind.FUNCTION

    assert {(edge.module, edge.imported_name, edge.alias) for edge in indexed.imports} == {
        ("asyncio", None, None),
        ("demo.tools", "Tool", "ToolAlias"),
    }


def test_chunk_ids_are_stable_and_keep_line_evidence(tmp_path: Path) -> None:
    _build_repository(tmp_path)
    manifest = RepositoryScanner().scan(tmp_path)
    indexer = PythonSourceIndexer()

    first = indexer.build(tmp_path, manifest)
    second = indexer.build(tmp_path, manifest)

    assert [chunk.chunk_id for chunk in first.chunks] == [chunk.chunk_id for chunk in second.chunks]
    greet = next(chunk for chunk in first.chunks if chunk.symbol == "Greeter.greet")
    assert greet.start_line == 8
    assert greet.end_line == 15
    assert "async def greet" in greet.content
    assert len(greet.content_hash) == 64


def test_long_symbols_are_split_with_bounded_overlap(tmp_path: Path) -> None:
    body = "\n".join(f"    value_{index} = {index}" for index in range(14))
    _build_repository(tmp_path, f"def long_function():\n{body}\n    return value_13\n")
    manifest = RepositoryScanner().scan(tmp_path)

    indexed = PythonSourceIndexer(IndexPolicy(max_chunk_lines=5, overlap_lines=1)).build(tmp_path, manifest)
    symbol_chunks = [chunk for chunk in indexed.chunks if chunk.symbol == "long_function"]

    assert len(symbol_chunks) == 4
    assert all(chunk.end_line - chunk.start_line + 1 <= 5 for chunk in symbol_chunks)
    assert symbol_chunks[1].start_line == symbol_chunks[0].end_line


def test_syntax_error_degrades_to_line_chunks(tmp_path: Path) -> None:
    _build_repository(tmp_path, "def broken(:\n    pass\n")
    manifest = RepositoryScanner().scan(tmp_path)

    indexed = PythonSourceIndexer().build(tmp_path, manifest)

    assert indexed.symbols == ()
    assert len(indexed.chunks) == 1
    assert indexed.chunks[0].symbol_kind == SymbolKind.MODULE
    assert "AST parsing failed" in indexed.warnings[0]


def test_source_changed_after_scan_is_not_indexed(tmp_path: Path) -> None:
    _build_repository(tmp_path)
    manifest = RepositoryScanner().scan(tmp_path)
    (tmp_path / "demo" / "service.py").write_text("CHANGED = True\n", encoding="utf-8")

    indexed = PythonSourceIndexer().build(tmp_path, manifest)

    assert indexed.indexed_files == 0
    assert indexed.chunks == ()
    assert indexed.warnings == ("source changed after manifest scan: demo/service.py",)


def test_index_policy_rejects_invalid_overlap() -> None:
    try:
        IndexPolicy(max_chunk_lines=5, overlap_lines=5)
    except ValueError as exc:
        assert str(exc) == "overlap_lines must be smaller than max_chunk_lines"
    else:
        raise AssertionError("invalid overlap was accepted")
