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
    """Tutor 生成的一个学习单元及其源码证据。"""

    sequence: int = Field(ge=1, le=10)
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=600)
    why_it_matters: str = Field(min_length=1, max_length=600)
    exercise: str = Field(min_length=1, max_length=600)
    evidence_ids: list[str] = Field(default_factory=list, max_length=5)


class QuizQuestionDraft(StrictModel):
    """绑定学习单元、评分点和引用证据的一道题。"""

    question_id: str = Field(min_length=1, max_length=80)
    unit_sequence: int = Field(ge=1, le=10)
    difficulty: QuizDifficulty
    prompt: str = Field(min_length=1, max_length=800)
    evaluation_points: list[str] = Field(default_factory=list, max_length=6)
    evidence_ids: list[str] = Field(default_factory=list, max_length=5)


class LearningPlanDraft(StrictModel):
    """模型生成、尚未经过确定性证据审查的完整学习计划。"""

    summary: str = Field(min_length=1, max_length=2_000)
    units: list[LearningUnitDraft] = Field(default_factory=list, max_length=5)
    questions: list[QuizQuestionDraft] = Field(default_factory=list, max_length=15)


class LearningPlan(StrictModel):
    """审查后的学习路径、练习、题目和最终引用集合。"""

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
        """标记为证据化的计划必须同时具有单元、题目和引用。"""
        if self.status == LearningPlanStatus.SOURCE_GROUNDED and not all(
            (self.units, self.questions, self.evidence)
        ):
            raise ValueError("source-grounded learning plans require units, questions, and evidence")
        return self


class AnswerSubmission(StrictModel):
    """用户对一道题提交的原始文本答案。"""

    question_id: str = Field(min_length=1, max_length=80)
    answer: str = Field(default="", max_length=8_000)


class QuizSubmission(StrictModel):
    """绑定报告、学习计划和仓库快照的一整份答题文件。"""

    schema_version: str = "1.0"
    report_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    answers: list[AnswerSubmission] = Field(default_factory=list, max_length=100)
    submitted_at: datetime | None = None

    @model_validator(mode="after")
    def validate_unique_answers(self) -> QuizSubmission:
        """一份提交中每个问题只能出现一次。"""
        question_ids = [item.question_id for item in self.answers]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("quiz submission contains duplicate question IDs")
        return self


class AnswerAssessmentDraft(StrictModel):
    """模型给出的单题评分草稿，后续仍需证据和分数校验。"""

    question_id: str = Field(min_length=1, max_length=80)
    score: int | None = Field(default=None, ge=0, le=100)
    feedback: str = Field(min_length=1, max_length=2_000)
    strengths: list[str] = Field(default_factory=list, max_length=6)
    gaps: list[str] = Field(default_factory=list, max_length=6)
    evidence_ids: list[str] = Field(default_factory=list, max_length=5)


class AnswerAssessment(StrictModel):
    """通过程序校验后的单题状态、分数和改进建议。"""

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
        """只有真正完成语义评审的答案可以带分数。"""
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
    """从全部单题结果确定性汇总出的完成度、掌握度和薄弱单元。"""

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
    """答案评审模式、逐题结果、学习进度和使用证据的总报告。"""

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
