"""验证教学阶段的源码证据选择策略。

测试确认选择器会综合架构、入口、测试和依赖等来源，同时遵守查询数、结果数和总证据预算，并保持
去重与确定性顺序。
"""

from __future__ import annotations

from pathlib import Path

from vibeproof.agents.analyst import RepositoryAnalystAgent
from vibeproof.llm.client import MockAnalystModelClient
from vibeproof.repository.evidence_aliases import EvidenceAliases
from vibeproof.repository.index import PythonSourceIndexer
from vibeproof.repository.learning_evidence import LearningEvidencePolicy, LearningEvidenceSelector
from vibeproof.repository.scanner import RepositoryScanner
from vibeproof.repository.store import EvidenceStore


def test_evidence_aliases_hide_long_ids_and_restore_them_deterministically() -> None:
    aliases = EvidenceAliases.from_chunk_ids(["chunk:sha256:first", "chunk:sha256:second"])

    assert aliases.aliases(["chunk:sha256:first", "chunk:sha256:second"]) == ["E1", "E2"]
    assert aliases.resolve_all(["E2", "E1"]) == ["chunk:sha256:second", "chunk:sha256:first"]
    assert aliases.resolve_all(["E1、", "、E2", "`E1`"]) == [
        "chunk:sha256:first",
        "chunk:sha256:second",
        "chunk:sha256:first",
    ]
    assert aliases.resolve_all(["E1、E2", "[E2 / E1]"]) == [
        "chunk:sha256:first",
        "chunk:sha256:second",
        "chunk:sha256:second",
        "chunk:sha256:first",
    ]
    assert aliases.resolve_all(["E1】【、】【E2", "《E2》「E1」"]) == [
        "chunk:sha256:first",
        "chunk:sha256:second",
        "chunk:sha256:second",
        "chunk:sha256:first",
    ]
    assert aliases.resolve("E99") == "E99"
    assert aliases.resolve_all(["evidence E1 and E2"]) == ["evidence E1 and E2"]


def test_default_tutor_budget_can_reuse_full_analyst_evidence_budget() -> None:
    assert LearningEvidencePolicy().max_evidence == 20


def _indexed_repository(tmp_path: Path):
    repository = tmp_path / "repository"
    tests = repository / "tests"
    tests.mkdir(parents=True)
    (repository / "main.py").write_text(
        "def repository_entrypoint() -> str:\n    return 'ready'\n",
        encoding="utf-8",
    )
    (tests / "test_main.py").write_text(
        "from main import repository_entrypoint\n\n"
        "def test_entrypoint():\n"
        "    assert repository_entrypoint() == 'ready'\n",
        encoding="utf-8",
    )
    manifest = RepositoryScanner().scan(repository)
    indexed = PythonSourceIndexer().build(repository, manifest)
    store = EvidenceStore(tmp_path / "index.sqlite3")
    store.replace_snapshot(manifest.repository_name, manifest.snapshot_id, indexed)
    architecture = RepositoryAnalystAgent(store, MockAnalystModelClient()).run(manifest)
    return manifest, store, architecture


def test_selector_combines_architecture_and_test_evidence(tmp_path: Path) -> None:
    manifest, store, architecture = _indexed_repository(tmp_path)
    selector = LearningEvidenceSelector(store, LearningEvidencePolicy(max_evidence=8))

    selection = selector.select(manifest, architecture)

    paths = {item.path for item in selection.evidence}
    assert "main.py" in paths
    assert "tests/test_main.py" in paths
    assert len(selection.evidence) <= 8
    assert len({item.chunk_id for item in selection.evidence}) == len(selection.evidence)


def test_store_reloads_bounded_hits_in_requested_order(tmp_path: Path) -> None:
    manifest, store, architecture = _indexed_repository(tmp_path)
    requested = [item.chunk_id for item in reversed(architecture.evidence)]

    hits = store.get_hits(manifest.snapshot_id, requested, max_excerpt_characters=40)

    assert [item.chunk_id for item in hits] == requested
    assert all(len(item.excerpt) <= 41 for item in hits)
