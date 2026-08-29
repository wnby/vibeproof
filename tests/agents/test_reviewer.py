"""验证答案评审 Agent 的身份、评分和引用约束。

测试覆盖 Mock 结构校验、真实评分分支、空答案、低分建议、未知题目、快照不一致及模型越权引用，确保
学习进度不会建立在伪造证据或无效模型输出上。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support import review_context
from vibeproof.agents.reviewer import AnswerReviewAgent
from vibeproof.core.models import (
    AnswerAssessmentStatus,
    AnswerSubmission,
    ReviewMode,
)
from vibeproof.llm.client import (
    MockAnswerReviewModelClient,
    ModelMessage,
)


class ScriptedReviewModel:
    provider = "scripted"
    model = "semantic-review-fixture"

    def __init__(self, score: int = 85, invented_evidence: bool = False):
        self.score = score
        self.invented_evidence = invented_evidence
        self.calls = 0

    def complete(self, messages: list[ModelMessage], *, output=None) -> str:
        self.calls += 1
        state = json.loads(messages[-1].content.split("ANSWER_REVIEW_STATE_JSON:\n", 1)[1])
        question = state["question"]
        return json.dumps(
            {
                "question_id": question["question_id"],
                "score": self.score,
                "feedback": "The explanation is checked against the supplied source.",
                "strengths": ["Identifies the responsibility"],
                "gaps": [] if self.score >= 70 else ["Explain the caller and return flow"],
                "evidence_ids": ["chunk:invented"] if self.invented_evidence else question["evidence_ids"],
            }
        )


def test_mock_review_is_explicitly_structure_only(tmp_path: Path) -> None:
    report, submission, store = review_context(tmp_path)
    submission.answers[0].answer = "The entrypoint constructs DemoService and returns execute()."

    review = AnswerReviewAgent(store, MockAnswerReviewModelClient()).run(report, submission)

    assert review.mode == ReviewMode.STRUCTURE_ONLY
    assert review.progress.answered_questions == 1
    assert review.progress.assessed_questions == 0
    assert review.progress.mastery_percent == 0
    assert review.assessments[0].status == AnswerAssessmentStatus.NOT_ASSESSED
    assert review.assessments[0].score is None
    assert "does not semantically score" in review.warnings[0]


def test_semantic_review_scores_grounded_answer(tmp_path: Path) -> None:
    report, submission, store = review_context(tmp_path)
    submission.answers[0].answer = "The function creates DemoService, calls execute, and returns its string."
    model = ScriptedReviewModel(score=86)

    review = AnswerReviewAgent(store, model).run(report, submission)

    assessment = review.assessments[0]
    assert review.mode == ReviewMode.MODEL_ASSESSED
    assert assessment.status == AnswerAssessmentStatus.ANSWERED
    assert assessment.score == 86
    assert review.progress.passed_questions == 1
    assert model.calls == 1


def test_low_score_recommends_learning_unit(tmp_path: Path) -> None:
    report, submission, store = review_context(tmp_path)
    submission.answers[0].answer = "It returns ready."

    review = AnswerReviewAgent(store, ScriptedReviewModel(score=42)).run(report, submission)

    assert review.assessments[0].status == AnswerAssessmentStatus.NEEDS_IMPROVEMENT
    assert review.assessments[0].unit_sequence in review.progress.weak_units
    assert review.progress.needs_improvement == 1


def test_blank_answer_is_not_sent_to_model(tmp_path: Path) -> None:
    report, submission, store = review_context(tmp_path)
    model = ScriptedReviewModel()

    review = AnswerReviewAgent(store, model).run(report, submission)

    assert all(item.status == AnswerAssessmentStatus.NOT_ASSESSED for item in review.assessments)
    assert model.calls == 0


def test_review_rejects_unknown_question_id(tmp_path: Path) -> None:
    report, submission, store = review_context(tmp_path)
    submission.answers.append(AnswerSubmission(question_id="invented", answer="answer"))

    with pytest.raises(ValueError, match="unknown question IDs"):
        AnswerReviewAgent(store, ScriptedReviewModel()).run(report, submission)


def test_review_rejects_mismatched_snapshot(tmp_path: Path) -> None:
    report, submission, store = review_context(tmp_path)
    submission.snapshot_id = "sha256:stale"

    with pytest.raises(ValueError, match="snapshot IDs must match"):
        AnswerReviewAgent(store, ScriptedReviewModel()).run(report, submission)


def test_model_citation_outside_question_is_rejected(tmp_path: Path) -> None:
    report, submission, store = review_context(tmp_path)
    submission.answers[0].answer = "An answer with an invented model citation."

    review = AnswerReviewAgent(store, ScriptedReviewModel(invented_evidence=True)).run(report, submission)

    assert review.assessments[0].status == AnswerAssessmentStatus.REJECTED
    assert review.assessments[0].score is None
    assert "outside this question" in review.assessments[0].feedback
