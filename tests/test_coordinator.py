"""验证统一接管协调器的阶段编排和降级策略。

测试检查完整流程、学习阶段、实际运行、模型异常和快照变化等情况，确保阶段失败能转成可信的
COMPLETED、PARTIAL、FAILED 或 SNAPSHOT_CHANGED 状态并保留已有产物。
"""

from __future__ import annotations

import sys
from pathlib import Path

from vibeproof.coordinator import TakeoverCoordinator, TakeoverPolicy
from vibeproof.evidence_store import EvidenceStore
from vibeproof.model_client import MockAnalystModelClient, ModelClientError, ModelMessage
from vibeproof.runtime import RuntimePolicy
from vibeproof.schemas import (
    AgentRunStatus,
    RuntimeStatus,
    StageStatus,
    TakeoverReport,
    TakeoverStage,
    TakeoverStatus,
)
from vibeproof.takeover_reporting import render_takeover_report


class FailingModel:
    provider = "failing"
    model = "unavailable-model"

    def complete(self, messages: list[ModelMessage]) -> str:
        raise ModelClientError("provider unavailable")


class FailingTutorModel:
    provider = "failing-tutor"
    model = "unavailable-tutor"

    def complete(self, messages: list[ModelMessage]) -> str:
        raise ModelClientError("tutor unavailable")


def _repository(tmp_path: Path, test_body: str = "def test_ok():\n    assert True\n") -> Path:
    repository = tmp_path / "repository"
    tests = repository / "tests"
    tests.mkdir(parents=True)
    (repository / "main.py").write_text(
        "def repository_entrypoint() -> str:\n    return 'ready'\n",
        encoding="utf-8",
    )
    (tests / "test_sample.py").write_text(test_body, encoding="utf-8")
    return repository


def _coordinator(
    tmp_path: Path,
    *,
    model=None,
    tutor_model=None,
    policy: TakeoverPolicy | None = None,
) -> TakeoverCoordinator:
    return TakeoverCoordinator(
        store=EvidenceStore(tmp_path / "state" / "index.sqlite3"),
        model=model or MockAnalystModelClient(),
        tutor_model=tutor_model,
        policy=policy,
    )


def test_unified_takeover_builds_every_artifact_without_execution(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    report = _coordinator(tmp_path).run(repository)

    assert report.status == TakeoverStatus.COMPLETED
    assert report.repository is not None
    assert report.source_index is not None
    assert report.architecture is not None
    assert report.learning_plan is not None
    assert report.runtime is not None
    assert report.runtime.status == RuntimeStatus.PLANNED
    assert report.runtime.executed is False
    assert report.snapshot_id == report.repository.snapshot_id
    assert report.snapshot_id == report.source_index.snapshot_id
    assert report.snapshot_id == report.architecture.snapshot_id
    assert report.snapshot_id == report.learning_plan.snapshot_id
    assert report.snapshot_id == report.runtime.before_snapshot_id
    assert [step.stage for step in report.steps] == [
        TakeoverStage.SCAN,
        TakeoverStage.INDEX,
        TakeoverStage.ANALYZE,
        TakeoverStage.LEARNING_PLAN,
        TakeoverStage.RUNTIME_PLAN,
        TakeoverStage.REPORT,
    ]
    assert report.architecture.claims
    assert report.learning_plan.units
    assert report.learning_plan.questions
    restored = TakeoverReport.model_validate_json(report.model_dump_json())
    assert restored.snapshot_id == report.snapshot_id


def test_model_failure_produces_partial_report_and_runtime_plan(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    report = _coordinator(tmp_path, model=FailingModel()).run(repository)

    assert report.status == TakeoverStatus.PARTIAL
    assert report.source_index is not None
    assert report.architecture is not None
    assert report.architecture.run_status == AgentRunStatus.MODEL_ERROR
    assert report.learning_plan is None
    assert report.runtime is not None
    assert report.runtime.status == RuntimeStatus.PLANNED
    analyze_step = next(step for step in report.steps if step.stage == TakeoverStage.ANALYZE)
    assert analyze_step.status == StageStatus.FAILED
    assert analyze_step.error == "provider unavailable"


def test_tutor_failure_produces_partial_report_without_losing_other_artifacts(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    report = _coordinator(tmp_path, tutor_model=FailingTutorModel()).run(repository)

    assert report.status == TakeoverStatus.PARTIAL
    assert report.architecture is not None
    assert report.architecture.run_status == AgentRunStatus.COMPLETED
    assert report.learning_plan is not None
    assert report.learning_plan.status.value == "FAILED"
    assert report.runtime is not None
    assert report.runtime.status == RuntimeStatus.PLANNED
    learning_step = next(step for step in report.steps if step.stage == TakeoverStage.LEARNING_PLAN)
    assert learning_step.status == StageStatus.FAILED
    assert learning_step.error == "tutor unavailable"


def test_failing_tests_are_preserved_in_partial_takeover_report(tmp_path: Path) -> None:
    repository = _repository(tmp_path, "def test_nope():\n    assert False\n")
    policy = TakeoverPolicy(
        execute_runtime=True,
        python_executable=sys.executable,
        runtime_policy=RuntimePolicy(timeout_seconds=20),
    )

    report = _coordinator(tmp_path, policy=policy).run(repository)

    assert report.status == TakeoverStatus.PARTIAL
    assert report.runtime is not None
    assert report.runtime.status == RuntimeStatus.FAILED
    assert report.runtime.evidence is not None
    assert report.runtime.evidence.exit_code == 1
    assert "1 failed" in report.runtime.evidence.stdout_excerpt
    runtime_step = next(step for step in report.steps if step.stage == TakeoverStage.RUNTIME_EXECUTION)
    assert runtime_step.status == StageStatus.FAILED


def test_runtime_repository_write_becomes_snapshot_changed_report(tmp_path: Path) -> None:
    repository = _repository(
        tmp_path,
        "from pathlib import Path\n\ndef test_write():\n    Path('created-by-test.txt').write_text('changed')\n",
    )
    policy = TakeoverPolicy(execute_runtime=True, python_executable=sys.executable)

    report = _coordinator(tmp_path, policy=policy).run(repository)

    assert report.status == TakeoverStatus.SNAPSHOT_CHANGED
    assert report.runtime is not None
    assert report.runtime.status == RuntimeStatus.SNAPSHOT_CHANGED
    assert report.runtime.repository_changed is True
    assert (repository / "created-by-test.txt").is_file()


def test_scan_failure_still_returns_auditable_failure_report(tmp_path: Path) -> None:
    missing = tmp_path / "missing-repository"

    report = _coordinator(tmp_path).run(missing)

    assert report.status == TakeoverStatus.FAILED
    assert report.snapshot_id is None
    assert report.repository is None
    assert report.steps[0].stage == TakeoverStage.SCAN
    assert report.steps[0].status == StageStatus.FAILED
    assert report.steps[-1].stage == TakeoverStage.REPORT


def test_markdown_takeover_report_contains_all_major_sections(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    report = _coordinator(tmp_path).run(repository)

    rendered = render_takeover_report(report)

    assert "# Repository takeover report" in rendered
    assert "## Source index" in rendered
    assert "## Architecture analysis" in rendered
    assert "## Recommended learning path" in rendered
    assert "## Source-grounded quiz" in rendered
    assert "## Runtime verification" in rendered
    assert "## Workflow trace" in rendered
    assert "repository_entrypoint" in rendered
    assert "return 'ready'" not in rendered
