from __future__ import annotations

from pathlib import Path

import pytest

from vibeproof.analyst import RepositoryAnalystAgent
from vibeproof.evidence_store import EvidenceStore
from vibeproof.model_client import MockAnalystModelClient, MockTutorModelClient
from vibeproof.quiz import QuizFileError, create_quiz_submission, load_quiz_submission, load_takeover_report, write_json
from vibeproof.scanner import RepositoryScanner
from vibeproof.schemas import TakeoverReport, TakeoverStatus
from vibeproof.source_index import PythonSourceIndexer
from vibeproof.tutor import RepositoryTutorAgent


def _report(tmp_path: Path) -> tuple[TakeoverReport, EvidenceStore]:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "main.py").write_text(
        "def repository_entrypoint() -> str:\n    return 'ready'\n",
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
        summary="Quiz fixture",
        source_index=index,
        architecture=architecture,
        learning_plan=learning,
    )
    return report, store


def test_create_quiz_submission_preserves_report_identity_and_questions(tmp_path: Path) -> None:
    report, _ = _report(tmp_path)

    submission = create_quiz_submission(report)

    assert submission.report_id == report.report_id
    assert submission.plan_id == report.learning_plan.plan_id
    assert submission.snapshot_id == report.snapshot_id
    assert [item.question_id for item in submission.answers] == [
        item.question_id for item in report.learning_plan.questions
    ]
    assert all(item.answer == "" for item in submission.answers)


def test_quiz_json_round_trip(tmp_path: Path) -> None:
    report, _ = _report(tmp_path)
    report_path = tmp_path / "takeover.json"
    answer_path = tmp_path / "answers.json"
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    loaded_report = load_takeover_report(report_path)
    written = write_json(answer_path, create_quiz_submission(loaded_report))
    loaded_submission = load_quiz_submission(written)

    assert loaded_submission.report_id == report.report_id
    assert loaded_submission.answers


def test_create_quiz_rejects_report_without_learning_plan() -> None:
    report = TakeoverReport(
        repository_name="empty",
        status=TakeoverStatus.FAILED,
        summary="No learning plan",
    )

    with pytest.raises(QuizFileError, match="does not contain"):
        create_quiz_submission(report)


def test_load_quiz_explains_invalid_json(tmp_path: Path) -> None:
    invalid = tmp_path / "answers.json"
    invalid.write_text("not json", encoding="utf-8")

    with pytest.raises(QuizFileError, match="not valid VibeProof JSON"):
        load_quiz_submission(invalid)
