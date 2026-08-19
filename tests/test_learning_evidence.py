from __future__ import annotations

from pathlib import Path

from vibeproof.analyst import RepositoryAnalystAgent
from vibeproof.evidence_store import EvidenceStore
from vibeproof.learning_evidence import LearningEvidencePolicy, LearningEvidenceSelector
from vibeproof.model_client import MockAnalystModelClient
from vibeproof.scanner import RepositoryScanner
from vibeproof.source_index import PythonSourceIndexer


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
