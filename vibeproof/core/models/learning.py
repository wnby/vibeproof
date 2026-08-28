"""学习计划、测验提交和答案评审模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import Field, model_validator

from vibeproof.core.models.common import (
    AnswerAssessmentStatus,
    AnswerReviewStatus,
    LearningPlanStatus,
    QuizDifficulty,
    ReviewMode,
    StrictModel,
)
from vibeproof.core.models.repository import EvidenceReference


class LearningUnitDraft(StrictModel):
    sequence: int = Field(ge=1, le=10)
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=600)
    why_it_matters: str = Field(min_length=1, max_length=600)
    exercise: str = Field(min_length=1, max_length=600)
    evidence_ids: list[str] = Field(default_factory=list, max_length=5)


class QuizQuestionDraft(StrictModel):
    question_id: str = Field(min_length=1, max_length=80)
    unit_sequence: int = Field(ge=1, le=10)
    difficulty: QuizDifficulty
    prompt: str = Field(min_length=1, max_length=800)
    evaluation_points: list[str] = Field(default_factory=list, max_length=6)
    evidence_ids: list[str] = Field(default_factory=list, max_length=5)


class LearningPlanDraft(StrictModel):
    summary: str = Field(min_length=1, max_length=2_000)
    units: list[LearningUnitDraft] = Field(default_factory=list, max_length=5)
    questions: list[QuizQuestionDraft] = Field(default_factory=list, max_length=15)


class LearningPlan(StrictModel):
    plan_id: str = Field(default_factory=lambda: f"learning:{uuid4().hex}")
    repository_name: str
    snapshot_id: str
    status: LearningPlanStatus
    provider: str
    model: str
    summary: str
    units: list[LearningUnitDraft] = Field(default_factory=list)
    questions: list[QuizQuestionDraft] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    rejected_items: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_grounded_plan(self) -> LearningPlan:
        if self.status == LearningPlanStatus.SOURCE_GROUNDED and not all(
            (self.units, self.questions, self.evidence)
        ):
            raise ValueError("source-grounded learning plans require units, questions, and evidence")
        return self


class AnswerSubmission(StrictModel):
    question_id: str = Field(min_length=1, max_length=80)
    answer: str = Field(default="", max_length=8_000)


class QuizSubmission(StrictModel):
    schema_version: str = "1.0"
    report_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    answers: list[AnswerSubmission] = Field(default_factory=list, max_length=100)
    submitted_at: datetime | None = None

    @model_validator(mode="after")
    def validate_unique_answers(self) -> QuizSubmission:
        question_ids = [item.question_id for item in self.answers]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("quiz submission contains duplicate question IDs")
        return self


class AnswerAssessmentDraft(StrictModel):
    question_id: str = Field(min_length=1, max_length=80)
    score: int | None = Field(default=None, ge=0, le=100)
    feedback: str = Field(min_length=1, max_length=2_000)
    strengths: list[str] = Field(default_factory=list, max_length=6)
    gaps: list[str] = Field(default_factory=list, max_length=6)
    evidence_ids: list[str] = Field(default_factory=list, max_length=5)


class AnswerAssessment(StrictModel):
    question_id: str = Field(min_length=1, max_length=80)
    unit_sequence: int = Field(ge=1, le=10)
    status: AnswerAssessmentStatus
    score: int | None = Field(default=None, ge=0, le=100)
    feedback: str = Field(min_length=1, max_length=2_000)
    strengths: list[str] = Field(default_factory=list, max_length=6)
    gaps: list[str] = Field(default_factory=list, max_length=6)
    evidence_ids: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_score_state(self) -> AnswerAssessment:
        assessed = self.status in {
            AnswerAssessmentStatus.ANSWERED,
            AnswerAssessmentStatus.NEEDS_IMPROVEMENT,
        }
        if assessed and self.score is None:
            raise ValueError("semantically assessed answers require a score")
        if not assessed and self.score is not None:
            raise ValueError("unassessed or rejected answers cannot have a score")
        return self


class LearningProgress(StrictModel):
    total_questions: int = Field(ge=0)
    answered_questions: int = Field(ge=0)
    assessed_questions: int = Field(ge=0)
    passed_questions: int = Field(ge=0)
    needs_improvement: int = Field(ge=0)
    not_assessed: int = Field(ge=0)
    rejected: int = Field(ge=0)
    completion_percent: float = Field(ge=0, le=100)
    mastery_percent: float = Field(ge=0, le=100)
    weak_units: list[int] = Field(default_factory=list)
    recommended_next_units: list[int] = Field(default_factory=list)


class AnswerReviewReport(StrictModel):
    review_id: str = Field(default_factory=lambda: f"answer-review:{uuid4().hex}")
    report_id: str
    plan_id: str
    repository_name: str
    snapshot_id: str
    status: AnswerReviewStatus
    mode: ReviewMode
    provider: str
    model: str
    assessments: list[AnswerAssessment] = Field(default_factory=list)
    progress: LearningProgress
    evidence: list[EvidenceReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
