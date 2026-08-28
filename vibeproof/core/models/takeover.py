"""完整仓库接管工作流的汇总模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import Field, model_validator

from vibeproof.core.models.analysis import ArchitectureReport
from vibeproof.core.models.common import (
    EvidenceKind,
    StageStatus,
    StrictModel,
    TakeoverStage,
    TakeoverStatus,
    VerificationStatus,
)
from vibeproof.core.models.learning import LearningPlan
from vibeproof.core.models.repository import SourceIndexSummary
from vibeproof.core.models.runtime import RuntimeVerificationReport


class Evidence(StrictModel):
    """统一描述清单、源码、运行或用户答案支持的一条事实。"""

    evidence_id: str = Field(default_factory=lambda: f"evidence:{uuid4().hex}")
    kind: EvidenceKind
    status: VerificationStatus
    claim: str = Field(min_length=1)
    source_path: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    command: list[str] | None = None
    exit_code: int | None = None
    output_excerpt: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_evidence_location(self) -> Evidence:
        """根据证据类型检查必需的源码位置或运行命令。"""
        if self.kind == EvidenceKind.SOURCE and not self.source_path:
            raise ValueError("source evidence requires source_path")
        if (self.start_line is not None or self.end_line is not None) and not self.source_path:
            raise ValueError("line evidence requires source_path")
        if self.start_line is not None and self.end_line is not None and self.end_line < self.start_line:
            raise ValueError("end_line cannot be before start_line")
        if self.kind == EvidenceKind.RUNTIME and not self.command:
            raise ValueError("runtime evidence requires a tokenized command")
        return self


class RepositorySummary(StrictModel):
    """从详细 Manifest 压缩出的报告首页仓库概况。"""

    repository_name: str
    snapshot_id: str
    languages: dict[str, int] = Field(default_factory=dict)
    frameworks: list[str] = Field(default_factory=list)
    entrypoints: list[str] = Field(default_factory=list)
    dependency_files: list[str] = Field(default_factory=list)
    test_files: list[str] = Field(default_factory=list)
    scanned_files: int = Field(ge=0)


class TakeoverStep(StrictModel):
    """完整接管中一个阶段的状态、耗时和可选错误。"""

    step: int = Field(ge=1)
    stage: TakeoverStage
    status: StageStatus
    summary: str
    duration_ms: int = Field(ge=0)
    error: str | None = None


class TakeoverReport(StrictModel):
    """用户最终获得的总产物，组合所有已完成阶段及已知限制。"""

    report_id: str = Field(default_factory=lambda: f"takeover:{uuid4().hex}")
    repository_name: str
    snapshot_id: str | None = None
    status: TakeoverStatus
    summary: str
    repository: RepositorySummary | None = None
    source_index: SourceIndexSummary | None = None
    architecture: ArchitectureReport | None = None
    learning_plan: LearningPlan | None = None
    runtime: RuntimeVerificationReport | None = None
    steps: list[TakeoverStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_completed_report(self) -> TakeoverReport:
        """只有所有核心阶段产物齐全时才允许标记为完成。"""
        if self.status == TakeoverStatus.COMPLETED and not all(
            (self.repository, self.source_index, self.architecture, self.learning_plan, self.runtime)
        ):
            raise ValueError("completed takeover reports require every workflow artifact")
        if self.repository is not None and self.snapshot_id != self.repository.snapshot_id:
            raise ValueError("report and repository snapshot IDs must match")
        return self
