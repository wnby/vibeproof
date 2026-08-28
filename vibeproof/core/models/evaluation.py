"""确定性 Agent Eval 的用例、指标和报告模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import Field, model_validator

from vibeproof.core.models.common import (
    EvaluationMetricStatus,
    EvaluationStatus,
    RuntimeStatus,
    StrictModel,
    TakeoverStatus,
)
from vibeproof.core.models.takeover import TakeoverReport


class EvaluationExpectations(StrictModel):
    """一个 Eval 场景对状态、数量、引用和运行结果的显式门槛。"""

    expected_takeover_status: TakeoverStatus = TakeoverStatus.COMPLETED
    expected_runtime_status: RuntimeStatus = RuntimeStatus.PLANNED
    minimum_claims: int = Field(default=1, ge=0, le=100)
    maximum_rejected_claims: int = Field(default=0, ge=0, le=100)
    minimum_learning_units: int = Field(default=1, ge=0, le=10)
    minimum_quiz_questions: int = Field(default=1, ge=0, le=100)
    maximum_model_failures: int = Field(default=0, ge=0, le=100)
    required_evidence_paths: list[str] = Field(default_factory=list, max_length=100)
    require_source_grounded_learning: bool = True
    require_unit_question_coverage: bool = True
    require_current_snapshot_citations: bool = True
    require_unchanged_repository: bool = True


class EvaluationCase(StrictModel):
    """可复现的 Eval 场景标识、说明和期望集合。"""

    schema_version: str = "1.0"
    case_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1_000)
    expectations: EvaluationExpectations = Field(default_factory=EvaluationExpectations)


class EvaluationMetric(StrictModel):
    """一个实际值与期望值的确定性比较结果。"""

    code: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    status: EvaluationMetricStatus
    actual: str = Field(max_length=2_000)
    expected: str = Field(max_length=2_000)
    detail: str = Field(default="", max_length=4_000)


class ModelCallSummary(StrictModel):
    """某个 Agent 任务的模型调用次数、失败数和耗时。"""

    task: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    calls: int = Field(ge=0)
    failures: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class EvaluationReport(StrictModel):
    """Eval 指标、模型观测和原始 Takeover 报告的组合产物。"""

    evaluation_id: str = Field(default_factory=lambda: f"evaluation:{uuid4().hex}")
    case_id: str
    case_name: str
    repository_name: str
    snapshot_id: str | None = None
    status: EvaluationStatus
    provider: str
    model: str
    duration_ms: int = Field(ge=0)
    passed_metrics: int = Field(ge=0)
    failed_metrics: int = Field(ge=0)
    info_metrics: int = Field(ge=0)
    metrics: list[EvaluationMetric] = Field(default_factory=list)
    model_calls: list[ModelCallSummary] = Field(default_factory=list)
    takeover: TakeoverReport
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_metric_summary(self) -> EvaluationReport:
        """确保汇总计数和最终状态与逐项指标完全一致。"""
        counts = {
            status: sum(item.status == status for item in self.metrics)
            for status in EvaluationMetricStatus
        }
        if self.passed_metrics != counts[EvaluationMetricStatus.PASS]:
            raise ValueError("passed_metrics does not match metric results")
        if self.failed_metrics != counts[EvaluationMetricStatus.FAIL]:
            raise ValueError("failed_metrics does not match metric results")
        if self.info_metrics != counts[EvaluationMetricStatus.INFO]:
            raise ValueError("info_metrics does not match metric results")
        expected_status = EvaluationStatus.FAILED if self.failed_metrics else EvaluationStatus.PASSED
        if self.status != expected_status:
            raise ValueError("evaluation status must reflect failed metric count")
        return self
