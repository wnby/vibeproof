"""跨测试模块共享的最小场景构造器。"""

from pathlib import Path

from vibeproof.agents.analyst import RepositoryAnalystAgent
from vibeproof.agents.tutor import RepositoryTutorAgent
from vibeproof.core.models import TakeoverReport, TakeoverStatus
from vibeproof.llm.client import MockAnalystModelClient, MockTutorModelClient
from vibeproof.repository.index import PythonSourceIndexer
from vibeproof.repository.scanner import RepositoryScanner
from vibeproof.repository.store import EvidenceStore
from vibeproof.workflows.quiz import create_quiz_submission


def review_context(tmp_path: Path):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "main.py").write_text(
        "class DemoService:\n"
        "    def execute(self) -> str:\n"
        "        return 'ready'\n\n"
        "def repository_entrypoint() -> str:\n"
        "    return DemoService().execute()\n",
        encoding="utf-8",
    )
    manifest = RepositoryScanner().scan(repository)
    indexed = PythonSourceIndexer().build(repository, manifest)
    store = EvidenceStore(tmp_path / "index.sqlite3")
    index = store.replace_snapshot(manifest.repository_name, manifest.snapshot_id, indexed)
    architecture = RepositoryAnalystAgent(store, MockAnalystModelClient()).run(manifest)
    learning = RepositoryTutorAgent(store, MockTutorModelClient()).run(manifest, architecture)
    report = TakeoverReport(
        repository_name=manifest.repository_name,
        snapshot_id=manifest.snapshot_id,
        status=TakeoverStatus.PARTIAL,
        summary="Review fixture",
        source_index=index,
        architecture=architecture,
        learning_plan=learning,
    )
    return report, create_quiz_submission(report), store
