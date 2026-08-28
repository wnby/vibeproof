"""运行计划、执行证据和验证报告模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import Field, model_validator

from vibeproof.core.models.common import InterpreterSource, RuntimeCheck, RuntimeStatus, StrictModel


class CommandPlan(StrictModel):
    """尚未执行的固定测试命令及其仓库快照。"""

    plan_id: str = Field(default_factory=lambda: f"command-plan:{uuid4().hex}")
    repository_name: str
    snapshot_id: str
    check: RuntimeCheck
    command: list[str] = Field(min_length=3)
    interpreter_source: InterpreterSource
    working_directory: str = "."
    timeout_seconds: float = Field(gt=0)
    output_limit_chars: int = Field(gt=0)
    executes_repository_code: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_catalog_command(self) -> CommandPlan:
        """拒绝固定目录之外的命令参数，避免计划被模型改写。"""
        expected_arguments = {
            RuntimeCheck.PYTEST: ["-m", "pytest", "-q"],
            RuntimeCheck.PYTEST_COLLECT: ["-m", "pytest", "--collect-only", "-q"],
        }
        if self.command[1:] != expected_arguments[self.check]:
            raise ValueError("command arguments must match the fixed runtime check catalog")
        return self


class RuntimeEvidence(StrictModel):
    """一次真实命令执行的退出码、受限输出、耗时和错误。"""

    evidence_id: str = Field(default_factory=lambda: f"runtime:{uuid4().hex}")
    plan_id: str
    check: RuntimeCheck
    status: RuntimeStatus
    command: list[str] = Field(min_length=3)
    exit_code: int | None = None
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    output_truncated: bool = False
    duration_ms: int = Field(ge=0)
    scrubbed_environment_variables: int = Field(default=0, ge=0)
    error: str | None = None
    started_at: datetime
    finished_at: datetime

    @model_validator(mode="after")
    def validate_runtime_status(self) -> RuntimeEvidence:
        """执行证据不能伪装成尚未执行的计划状态。"""
        if self.status in {RuntimeStatus.PLANNED, RuntimeStatus.SNAPSHOT_CHANGED}:
            raise ValueError("runtime evidence requires a command execution status")
        return self


class RuntimeVerificationReport(StrictModel):
    """将命令计划、可选执行证据和运行前后快照组合在一起。"""

    report_id: str = Field(default_factory=lambda: f"runtime-report:{uuid4().hex}")
    repository_name: str
    before_snapshot_id: str
    after_snapshot_id: str | None = None
    status: RuntimeStatus
    executed: bool
    repository_changed: bool = False
    plan: CommandPlan
    evidence: RuntimeEvidence | None = None
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_execution_state(self) -> RuntimeVerificationReport:
        """确保执行标记、证据、状态和仓库变化彼此一致。"""
        if self.executed and self.evidence is None:
            raise ValueError("executed runtime reports require evidence")
        if not self.executed and self.status != RuntimeStatus.PLANNED:
            raise ValueError("unexecuted runtime reports must be PLANNED")
        if self.repository_changed and self.status != RuntimeStatus.SNAPSHOT_CHANGED:
            raise ValueError("changed repositories must use SNAPSHOT_CHANGED status")
        return self
