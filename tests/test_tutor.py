from __future__ import annotations

import json
from pathlib import Path

from vibeproof.analyst import RepositoryAnalystAgent
from vibeproof.evidence_store import EvidenceStore
from vibeproof.learning_evidence import LearningEvidenceSelector
from vibeproof.model_client import MockAnalystModelClient, MockTutorModelClient, ModelMessage
from vibeproof.scanner import RepositoryScanner
from vibeproof.schemas import (
    LearningPlanDraft,
    LearningPlanStatus,
    LearningUnitDraft,
    QuizDifficulty,
    QuizQuestionDraft,
)
from vibeproof.source_index import PythonSourceIndexer
from vibeproof.tutor import LearningPlanReviewer, RepositoryTutorAgent


class InvalidTutorModel:
    provider = "invalid"
    model = "invalid-tutor"

    def complete(self, messages: list[ModelMessage]) -> str:
        return "not-json"


def _context(tmp_path: Path):
    repository = tmp_path / "repository"
    tests = repository / "tests"
    tests.mkdir(parents=True)
    (repository / "main.py").write_text(
        "class DemoService:\n    def execute(self) -> str:\n        return 'ready'\n\n"
        "def repository_entrypoint() -> str:\n    return DemoService().execute()\n",
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


def test_mock_tutor_generates_reviewed_units_and_questions(tmp_path: Path) -> None:
    manifest, store, architecture = _context(tmp_path)

    plan = RepositoryTutorAgent(store, MockTutorModelClient()).run(manifest, architecture)

    assert plan.status == LearningPlanStatus.SOURCE_GROUNDED
    assert plan.units
    assert len(plan.questions) == len(plan.units)
    assert [unit.sequence for unit in plan.units] == list(range(1, len(plan.units) + 1))
    evidence_ids = {item.chunk_id for item in plan.evidence}
    assert all(set(unit.evidence_ids) <= evidence_ids for unit in plan.units)
    assert all(set(question.evidence_ids) <= evidence_ids for question in plan.questions)


def test_reviewer_rejects_invented_evidence_and_dependent_question(tmp_path: Path) -> None:
    manifest, store, _ = _context(tmp_path)
    draft = LearningPlanDraft(
        summary="Invented plan",
        units=[
            LearningUnitDraft(
                sequence=1,
                title="Invented",
                objective="Explain invented code.",
                why_it_matters="It does not exist.",
                exercise="Find it.",
                evidence_ids=["chunk:invented"],
            )
        ],
        questions=[
            QuizQuestionDraft(
                question_id="q1",
                unit_sequence=1,
                difficulty=QuizDifficulty.BASIC,
                prompt="What does the invented code do?",
                evaluation_points=["Identify it"],
                evidence_ids=["chunk:invented"],
            )
        ],
    )

    review = LearningPlanReviewer(store).review(draft, {}, manifest.snapshot_id)

    assert review.units == ()
    assert review.questions == ()
    assert any("not supplied to the tutor" in item for item in review.rejected_items)
    assert any("rejected or missing learning unit" in item for item in review.rejected_items)


def test_reviewer_rejects_stale_observed_evidence(tmp_path: Path) -> None:
    manifest, store, architecture = _context(tmp_path)
    selection = LearningEvidenceSelector(store).select(manifest, architecture)
    hit = selection.evidence[0]
    stale = hit.model_copy(update={"snapshot_id": "sha256:stale"})
    draft = LearningPlanDraft(
        summary="Stale plan",
        units=[
            LearningUnitDraft(
                sequence=1,
                title="Stale",
                objective="Explain the source.",
                why_it_matters="Snapshot integrity matters.",
                exercise="Compare snapshots.",
                evidence_ids=[hit.chunk_id],
            )
        ],
    )

    review = LearningPlanReviewer(store).review(
        draft,
        {hit.chunk_id: stale},
        manifest.snapshot_id,
    )

    assert review.units == ()
    assert "different snapshot" in review.rejected_items[0]


def test_invalid_tutor_output_becomes_failed_learning_plan(tmp_path: Path) -> None:
    manifest, store, architecture = _context(tmp_path)

    plan = RepositoryTutorAgent(store, InvalidTutorModel()).run(manifest, architecture)

    assert plan.status == LearningPlanStatus.FAILED
    assert plan.units == []
    assert "Invalid JSON" in plan.warnings[0]


def test_mock_tutor_output_is_deterministic_for_same_state(tmp_path: Path) -> None:
    manifest, store, architecture = _context(tmp_path)
    selection = LearningEvidenceSelector(store).select(manifest, architecture)
    state = {
        "repository": {"repository_name": manifest.repository_name},
        "evidence": [item.model_dump(mode="json") for item in selection.evidence],
    }
    messages = [ModelMessage(role="user", content=f"TUTOR_STATE_JSON:\n{json.dumps(state)}")]
    model = MockTutorModelClient()

    assert model.complete(messages) == model.complete(messages)
