"""验证确定性 Agent Eval 的指标计算、用例加载和固定场景。

测试覆盖成功报告、陈旧引用、缺失必需路径、非法用例文件，以及正常、故障、异步三个仓库场景，确保
评估结论来自明确期望和类型化产物，而不是模型自我打分。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from vibeproof.analyst import AnalystPolicy
from vibeproof.cli import main
from vibeproof.coordinator import TakeoverCoordinator, TakeoverPolicy
from vibeproof.evaluation_reporting import render_evaluation_report
from vibeproof.evaluator import EvaluationCaseError, RepositoryEvaluator, load_evaluation_case
from vibeproof.evidence_store import EvidenceStore
from vibeproof.model_client import MockAnalystModelClient, MockTutorModelClient
from vibeproof.schemas import (
    EvaluationCase,
    EvaluationExpectations,
    EvaluationMetricStatus,
    EvaluationStatus,
    RuntimeStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _takeover(tmp_path: Path):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "app.py").write_text(
        "def repository_entrypoint() -> str:\n    return 'ready'\n",
        encoding="utf-8",
    )
    (repository / "test_app.py").write_text(
        "from app import repository_entrypoint\n\n"
        "def test_entrypoint():\n"
        "    assert repository_entrypoint() == 'ready'\n",
        encoding="utf-8",
    )
    store = EvidenceStore(tmp_path / "index.sqlite3")
    report = TakeoverCoordinator(
        store=store,
        model=MockAnalystModelClient(),
        tutor_model=MockTutorModelClient(),
        policy=TakeoverPolicy(analyst_policy=AnalystPolicy(max_queries=5)),
    ).run(repository)
    return report


def test_default_evaluation_passes_grounded_plan_only_takeover(tmp_path: Path) -> None:
    takeover = _takeover(tmp_path)

    report = RepositoryEvaluator().evaluate(
        takeover,
        provider="mock",
        model="deterministic-analyst-v1",
        duration_ms=12,
    )

    assert report.status == EvaluationStatus.PASSED
    assert report.failed_metrics == 0
    assert any(item.code == "architecture_citations" for item in report.metrics)
    assert any(item.code == "stage_trace" and item.status == EvaluationMetricStatus.INFO for item in report.metrics)


def test_evaluation_fails_stale_architecture_citation(tmp_path: Path) -> None:
    takeover = _takeover(tmp_path).model_copy(deep=True)
    takeover.architecture.evidence[0].snapshot_id = "sha256:stale"

    report = RepositoryEvaluator().evaluate(
        takeover,
        provider="mock",
        model="deterministic-analyst-v1",
        duration_ms=1,
    )

    metric = next(item for item in report.metrics if item.code == "architecture_citations")
    assert report.status == EvaluationStatus.FAILED
    assert metric.status == EvaluationMetricStatus.FAIL


def test_evaluation_fails_when_required_path_was_not_observed(tmp_path: Path) -> None:
    takeover = _takeover(tmp_path)
    case = EvaluationCase(
        case_id="missing-path",
        name="Missing required evidence path",
        expectations=EvaluationExpectations(required_evidence_paths=["invented.py"]),
    )

    report = RepositoryEvaluator().evaluate(
        takeover,
        provider="mock",
        model="deterministic-analyst-v1",
        duration_ms=1,
        case=case,
    )

    metric = next(item for item in report.metrics if item.code == "required_evidence_paths")
    assert metric.status == EvaluationMetricStatus.FAIL
    assert "invented.py" in metric.detail


def test_markdown_evaluation_lists_metrics_and_interpretation(tmp_path: Path) -> None:
    takeover = _takeover(tmp_path)
    report = RepositoryEvaluator().evaluate(
        takeover,
        provider="mock",
        model="deterministic-analyst-v1",
        duration_ms=12,
    )

    rendered = render_evaluation_report(report)

    assert "# Agent evaluation" in rendered
    assert "Architecture citation integrity" in rendered
    assert "do not prove semantic correctness" in rendered


def test_invalid_evaluation_case_has_clear_error(tmp_path: Path) -> None:
    case_path = tmp_path / "invalid.json"
    case_path.write_text('{"case_id":"missing-fields"}', encoding="utf-8")

    with pytest.raises(EvaluationCaseError, match="not valid VibeProof JSON"):
        load_evaluation_case(case_path)


@pytest.mark.parametrize(
    ("fixture", "case_name", "execute", "runtime_status"),
    [
        ("healthy_service", "healthy_service.json", True, RuntimeStatus.PASSED),
        ("broken_service", "broken_service.json", True, RuntimeStatus.FAILED),
        ("ambiguous_agent", "ambiguous_agent.json", False, RuntimeStatus.PLANNED),
    ],
)
def test_committed_evaluation_cases_match_mock_expectations(
    tmp_path: Path,
    fixture: str,
    case_name: str,
    execute: bool,
    runtime_status: RuntimeStatus,
) -> None:
    output = tmp_path / f"{fixture}.json"
    arguments = [
        "eval",
        str(PROJECT_ROOT / "evals" / "fixtures" / fixture),
        "--case",
        str(PROJECT_ROOT / "evals" / "cases" / case_name),
        "--provider",
        "mock",
        "--database",
        str(tmp_path / f"{fixture}.sqlite3"),
        "--format",
        "json",
        "--output",
        str(output),
    ]
    if execute:
        arguments.extend(["--execute", "--python", sys.executable])

    exit_code = main(arguments)
    report = output.read_text(encoding="utf-8")

    assert exit_code == 0
    assert '"status": "PASSED"' in report
    assert f'"status": "{runtime_status.value}"' in report
