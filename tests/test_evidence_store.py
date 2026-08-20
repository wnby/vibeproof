"""验证 SQLite 源码证据仓库的写入、检索和快照隔离。

测试覆盖索引替换、符号与文本搜索、引用批量加载、摘录长度限制、结果排序以及缺失快照提示，保证上层
Agent 获取的是当前仓库版本中的确定性证据。
"""

from pathlib import Path

import pytest

from vibeproof.evidence_store import EvidenceStore, IndexNotFoundError
from vibeproof.scanner import RepositoryScanner
from vibeproof.source_index import PythonSourceIndexer

SOURCE = """from fastapi import APIRouter

router = APIRouter()


class ChatService:
    async def stream_chat(self, message: str) -> str:
        return message


@router.post("/chat")
async def chat_stream(service: ChatService) -> str:
    return await service.stream_chat("hello")
"""


def _indexed_store(tmp_path: Path) -> tuple[EvidenceStore, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "chat.py").write_text(SOURCE, encoding="utf-8")
    manifest = RepositoryScanner().scan(repository)
    indexed = PythonSourceIndexer().build(repository, manifest)
    store = EvidenceStore(tmp_path / "cache" / "index.sqlite3")
    store.replace_snapshot(manifest.repository_name, manifest.snapshot_id, indexed)
    return store, manifest.snapshot_id


def test_store_persists_summary_and_ranks_exact_symbol_first(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "chat.py").write_text(SOURCE, encoding="utf-8")
    manifest = RepositoryScanner().scan(repository)
    indexed = PythonSourceIndexer().build(repository, manifest)
    store = EvidenceStore(tmp_path / "cache" / "index.sqlite3")

    summary = store.replace_snapshot(manifest.repository_name, manifest.snapshot_id, indexed)
    hits = store.search(manifest.snapshot_id, "ChatService.stream_chat", limit=3)

    assert summary.indexed_files == 1
    assert summary.symbol_count == 3
    assert summary.chunk_count >= 4
    assert summary.import_count == 1
    assert Path(summary.database_path).is_file()
    assert hits[0].symbol == "ChatService.stream_chat"
    assert hits[0].path == "chat.py"
    assert hits[0].start_line == 7
    assert "async def stream_chat" in hits[0].excerpt


def test_search_supports_path_and_source_terms(tmp_path: Path) -> None:
    store, snapshot_id = _indexed_store(tmp_path)

    hits = store.search(snapshot_id, "router.post", limit=5)

    assert hits
    assert hits[0].symbol == "chat_stream"
    assert all(hit.score > 0 for hit in hits)


def test_search_requires_matching_snapshot(tmp_path: Path) -> None:
    store, _ = _indexed_store(tmp_path)

    with pytest.raises(IndexNotFoundError, match="snapshot is not indexed"):
        store.search("sha256:missing", "stream_chat")


def test_search_requires_existing_database(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "missing.sqlite3")

    with pytest.raises(IndexNotFoundError, match="does not exist"):
        store.search("sha256:missing", "stream_chat")


@pytest.mark.parametrize("query", ["", "   "])
def test_search_rejects_empty_query(tmp_path: Path, query: str) -> None:
    store, snapshot_id = _indexed_store(tmp_path)

    with pytest.raises(ValueError, match="query cannot be empty"):
        store.search(snapshot_id, query)


def test_replacing_same_snapshot_is_idempotent(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "chat.py").write_text(SOURCE, encoding="utf-8")
    manifest = RepositoryScanner().scan(repository)
    indexed = PythonSourceIndexer().build(repository, manifest)
    store = EvidenceStore(tmp_path / "index.sqlite3")

    first = store.replace_snapshot(manifest.repository_name, manifest.snapshot_id, indexed)
    second = store.replace_snapshot(manifest.repository_name, manifest.snapshot_id, indexed)

    assert first == second
    assert len(store.search(manifest.snapshot_id, "stream_chat", limit=100)) < 10


def test_store_loads_bounded_references_without_source_content(tmp_path: Path) -> None:
    store, snapshot_id = _indexed_store(tmp_path)
    hit = store.search(snapshot_id, "stream_chat", limit=1)[0]

    references = store.get_references(snapshot_id, [hit.chunk_id, hit.chunk_id, "chunk:missing"])

    assert list(references) == [hit.chunk_id]
    reference = references[hit.chunk_id]
    assert reference.path == hit.path
    assert not hasattr(reference, "excerpt")
