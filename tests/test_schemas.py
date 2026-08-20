"""验证跨模块 Pydantic 数据契约中的关键不变量。

测试主动构造合法与矛盾状态，检查源码行号、证据类型、运行计划、运行状态和完成报告等模型能否在系统
边界及时拒绝无效数据。
"""

import pytest
from pydantic import ValidationError

from vibeproof.schemas import (
    CommandPlan,
    Evidence,
    EvidenceKind,
    InterpreterSource,
    RuntimeCheck,
    RuntimeStatus,
    RuntimeVerificationReport,
    VerificationStatus,
)


def test_source_evidence_requires_a_path() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            kind=EvidenceKind.SOURCE,
            status=VerificationStatus.VERIFIED,
            claim="The API entry point exists.",
            created_by="test",
        )


def test_runtime_evidence_requires_tokenized_command() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            kind=EvidenceKind.RUNTIME,
            status=VerificationStatus.VERIFIED,
            claim="Tests passed.",
            created_by="test",
        )


def test_line_range_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            kind=EvidenceKind.SOURCE,
            status=VerificationStatus.VERIFIED,
            claim="The route calls the service.",
            source_path="app/api.py",
            start_line=20,
            end_line=10,
            created_by="test",
        )


def test_executed_runtime_report_requires_evidence() -> None:
    plan = CommandPlan(
        repository_name="demo",
        snapshot_id="sha256:demo",
        check=RuntimeCheck.PYTEST,
        command=["python", "-m", "pytest", "-q"],
        interpreter_source=InterpreterSource.CURRENT_PROCESS,
        timeout_seconds=10,
        output_limit_chars=100,
    )

    with pytest.raises(ValidationError):
        RuntimeVerificationReport(
            repository_name="demo",
            before_snapshot_id="sha256:demo",
            status=RuntimeStatus.PASSED,
            executed=True,
            plan=plan,
        )


def test_command_plan_rejects_arguments_outside_the_fixed_catalog() -> None:
    with pytest.raises(ValidationError):
        CommandPlan(
            repository_name="demo",
            snapshot_id="sha256:demo",
            check=RuntimeCheck.PYTEST,
            command=["python", "-m", "pytest", "--custom-command"],
            interpreter_source=InterpreterSource.CURRENT_PROCESS,
            timeout_seconds=10,
            output_limit_chars=100,
        )
