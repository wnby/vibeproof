"""本地 Web 接管任务、阶段状态和学习尝试的数据契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import Field

from vibeproof.core.models.common import RuntimeCheck, StrictModel, TakeoverStage
from vibeproof.core.models.learning import AnswerReviewReport, QuizSubmission
from vibeproof.core.models.takeover import TakeoverReport, TakeoverStep


class WebRunStatus(StrEnum):
    """Web 后台任务从排队到最终产物的生命周期。"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class WebRunConfiguration(StrictModel):
    """重放一次 Web 接管所需的非敏感配置。"""

    relative_path: str = Field(min_length=1, max_length=500)
    provider: str = Field(min_length=1, max_length=80)
    model: str | None = Field(default=None, max_length=200)
    analysis_depth: str = Field(default="deep", pattern="^(standard|deep)$")
    execute_runtime: bool = False
    runtime_check: RuntimeCheck = RuntimeCheck.PYTEST


class LearningAttempt(StrictModel):
    """一次用户答题、模型评审及其时间，用于保留多轮学习进度。"""

    attempt_id: str = Field(default_factory=lambda: f"attempt_{uuid4().hex}")
    submission: QuizSubmission
    review: AnswerReviewReport
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WebRunRecord(StrictModel):
    """可持久化、可轮询并可重新打开的一次仓库接管任务。"""

    schema_version: str = "1.0"
    run_id: str = Field(default_factory=lambda: f"run_{uuid4().hex}")
    configuration: WebRunConfiguration
    status: WebRunStatus = WebRunStatus.PENDING
    active_stage: TakeoverStage | None = None
    steps: list[TakeoverStep] = Field(default_factory=list)
    report: TakeoverReport | None = None
    attempts: list[LearningAttempt] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WebRunSummary(StrictModel):
    """最近任务列表使用的轻量摘要，不复制完整报告和源码引用。"""

    run_id: str
    repository_name: str
    relative_path: str
    status: WebRunStatus
    active_stage: TakeoverStage | None = None
    attempt_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime
