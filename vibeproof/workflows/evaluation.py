"""对仓库接管结果执行不依赖模型自评的确定性评估。

本模块读取预先声明的评估期望，检查工作流状态、引用快照、学习覆盖、必需证据路径和运行结果，并将
每项结果记录为可重复比较的指标；它不让被评估模型给自己打分。
"""

from __future__ import annotations

from pathlib import Path
from time import monotonic

from pydantic import ValidationError

from vibeproof.core.models import (
    AgentRunStatus,
    EvaluationCase,
    EvaluationExpectations,
    EvaluationMetric,
    EvaluationMetricStatus,
    EvaluationReport,
    EvaluationStatus,
    LearningPlanStatus,
    ModelCallSummary,
    StageStatus,
    TakeoverReport,
)
from vibeproof.llm.client import ModelClient, ModelMessage


class EvaluationCaseError(ValueError):
    pass


DEFAULT_EVALUATION_CASE = EvaluationCase(
    case_id="default-repository-evaluation",
    name="Default repository evaluation",
    description="Generic plan-only quality gate for a Python repository takeover.",
)


class ObservedModelClient:
    """Record call count, failures, and latency while preserving the ModelClient interface."""

    def __init__(self, task: str, client: ModelClient):
        self.task = task
        self.client = client
        self.provider = client.provider
        self.model = client.model
        self.calls = 0
        self.failures = 0
        self.duration_ms = 0

    def complete(self, messages: list[ModelMessage]) -> str:
        self.calls += 1
        started = monotonic()
        try:
            return self.client.complete(messages)
        except Exception:
            self.failures += 1
            raise
        finally:
            self.duration_ms += max(0, round((monotonic() - started) * 1_000))

    def summary(self) -> ModelCallSummary:
        return ModelCallSummary(
            task=self.task,
            provider=self.provider,
            model=self.model,
            calls=self.calls,
            failures=self.failures,
            duration_ms=self.duration_ms,
        )


class RepositoryEvaluator:
    def evaluate(
        self,
        takeover: TakeoverReport,
        *,
        provider: str,
        model: str,
        duration_ms: int,
        case: EvaluationCase | None = None,
        model_calls: list[ModelCallSummary] | None = None,
    ) -> EvaluationReport:
        selected_case = case or DEFAULT_EVALUATION_CASE
        expected = selected_case.expectations
        observed_calls = model_calls or []
        metrics = [
            self._takeover_status(takeover, expected),
            self._architecture_status(takeover),
            self._claim_count(takeover, expected),
            self._rejected_claim_count(takeover, expected),
            self._architecture_citations(takeover, expected),
            self._learning_status(takeover, expected),
            self._learning_unit_count(takeover, expected),
            self._quiz_question_count(takeover, expected),
            self._unit_question_coverage(takeover, expected),
            self._learning_citations(takeover, expected),
            self._required_paths(takeover, expected),
            self._runtime_status(takeover, expected),
            self._repository_unchanged(takeover, expected),
            self._model_failures(observed_calls, expected),
            self._stage_trace(takeover),
        ]
        passed = sum(item.status == EvaluationMetricStatus.PASS for item in metrics)
        failed = sum(item.status == EvaluationMetricStatus.FAIL for item in metrics)
        info = sum(item.status == EvaluationMetricStatus.INFO for item in metrics)
        warnings = [
            "These metrics validate workflow contracts and evidence provenance; they do not prove semantic correctness."
        ]
        if provider == "mock":
            warnings.append("The mock provider validates deterministic orchestration, not real-model answer quality.")
        return EvaluationReport(
            case_id=selected_case.case_id,
            case_name=selected_case.name,
            repository_name=takeover.repository_name,
            snapshot_id=takeover.snapshot_id,
            status=EvaluationStatus.FAILED if failed else EvaluationStatus.PASSED,
            provider=provider,
            model=model,
            duration_ms=duration_ms,
            passed_metrics=passed,
            failed_metrics=failed,
            info_metrics=info,
            metrics=metrics,
            model_calls=observed_calls,
            takeover=takeover,
            warnings=warnings,
        )

    @staticmethod
    def _takeover_status(report: TakeoverReport, expected: EvaluationExpectations) -> EvaluationMetric:
        actual = report.status.value
        target = expected.expected_takeover_status.value
        return _metric(
            "takeover_status",
            "Takeover workflow status",
            actual == target,
            actual,
            target,
            "The expected status may deliberately be PARTIAL for a known failing runtime fixture.",
        )

    @staticmethod
    def _architecture_status(report: TakeoverReport) -> EvaluationMetric:
        actual = report.architecture.run_status.value if report.architecture else "MISSING"
        target = AgentRunStatus.COMPLETED.value
        return _metric(
            "architecture_status",
            "Architecture agent structured result",
            actual == target,
            actual,
            target,
            "A completed result means the model output passed the architecture action contract.",
        )

    @staticmethod
    def _claim_count(report: TakeoverReport, expected: EvaluationExpectations) -> EvaluationMetric:
        actual = len(report.architecture.claims) if report.architecture else 0
        target = expected.minimum_claims
        return _metric(
            "accepted_claims",
            "Accepted architecture claims",
            actual >= target,
            str(actual),
            f">= {target}",
        )

    @staticmethod
    def _rejected_claim_count(report: TakeoverReport, expected: EvaluationExpectations) -> EvaluationMetric:
        actual = len(report.architecture.rejected_claims) if report.architecture else 0
        target = expected.maximum_rejected_claims
        return _metric(
            "rejected_claims",
            "Rejected architecture claims",
            actual <= target,
            str(actual),
            f"<= {target}",
            "Rejected claims expose invented, unseen, stale, or otherwise invalid citations.",
        )

    @staticmethod
    def _architecture_citations(report: TakeoverReport, expected: EvaluationExpectations) -> EvaluationMetric:
        architecture = report.architecture
        if architecture is None:
            valid, actual, detail = False, "0/0", "Architecture report is missing."
        else:
            references = {item.chunk_id: item for item in architecture.evidence}
            cited = [item for claim in architecture.claims for item in claim.evidence_ids]
            valid_ids = [
                item
                for item in cited
                if item in references and references[item].snapshot_id == report.snapshot_id
            ]
            valid = len(valid_ids) == len(cited) and all(claim.evidence_ids for claim in architecture.claims)
            actual = f"{len(valid_ids)}/{len(cited)}"
            detail = "Every accepted claim must cite evidence from the evaluated snapshot."
        if not expected.require_current_snapshot_citations:
            return _info("architecture_citations", "Architecture citation integrity", actual, "informational", detail)
        return _metric(
            "architecture_citations",
            "Architecture citation integrity",
            valid,
            actual,
            "all citations current",
            detail,
        )

    @staticmethod
    def _learning_status(report: TakeoverReport, expected: EvaluationExpectations) -> EvaluationMetric:
        actual = report.learning_plan.status.value if report.learning_plan else "MISSING"
        target = LearningPlanStatus.SOURCE_GROUNDED.value
        if not expected.require_source_grounded_learning:
            return _info("learning_status", "Learning plan status", actual, "informational")
        return _metric("learning_status", "Learning plan status", actual == target, actual, target)

    @staticmethod
    def _learning_unit_count(report: TakeoverReport, expected: EvaluationExpectations) -> EvaluationMetric:
        actual = len(report.learning_plan.units) if report.learning_plan else 0
        target = expected.minimum_learning_units
        return _metric("learning_units", "Learning units", actual >= target, str(actual), f">= {target}")

    @staticmethod
    def _quiz_question_count(report: TakeoverReport, expected: EvaluationExpectations) -> EvaluationMetric:
        actual = len(report.learning_plan.questions) if report.learning_plan else 0
        target = expected.minimum_quiz_questions
        return _metric("quiz_questions", "Quiz questions", actual >= target, str(actual), f">= {target}")

    @staticmethod
    def _unit_question_coverage(report: TakeoverReport, expected: EvaluationExpectations) -> EvaluationMetric:
        plan = report.learning_plan
        unit_ids = {item.sequence for item in plan.units} if plan else set()
        covered = {item.unit_sequence for item in plan.questions} if plan else set()
        missing = sorted(unit_ids - covered)
        actual = f"{len(unit_ids - set(missing))}/{len(unit_ids)}"
        detail = f"Units without questions: {', '.join(map(str, missing)) or 'none'}."
        if not expected.require_unit_question_coverage:
            return _info("unit_question_coverage", "Learning-unit question coverage", actual, "informational", detail)
        return _metric(
            "unit_question_coverage",
            "Learning-unit question coverage",
            bool(unit_ids) and not missing,
            actual,
            "all units covered",
            detail,
        )

    @staticmethod
    def _learning_citations(report: TakeoverReport, expected: EvaluationExpectations) -> EvaluationMetric:
        plan = report.learning_plan
        if plan is None:
            valid, actual, detail = False, "0/0", "Learning plan is missing."
        else:
            references = {item.chunk_id: item for item in plan.evidence}
            items = [*plan.units, *plan.questions]
            cited = [item for learning_item in items for item in learning_item.evidence_ids]
            valid_ids = [
                item
                for item in cited
                if item in references and references[item].snapshot_id == report.snapshot_id
            ]
            valid = len(valid_ids) == len(cited) and all(item.evidence_ids for item in items)
            actual = f"{len(valid_ids)}/{len(cited)}"
            detail = "Every learning unit and question must cite evidence from the evaluated snapshot."
        if not expected.require_current_snapshot_citations:
            return _info("learning_citations", "Learning citation integrity", actual, "informational", detail)
        return _metric(
            "learning_citations",
            "Learning citation integrity",
            valid,
            actual,
            "all citations current",
            detail,
        )

    @staticmethod
    def _required_paths(report: TakeoverReport, expected: EvaluationExpectations) -> EvaluationMetric:
        architecture_paths = {item.path for item in report.architecture.evidence} if report.architecture else set()
        learning_paths = {item.path for item in report.learning_plan.evidence} if report.learning_plan else set()
        observed = architecture_paths | learning_paths
        required = set(expected.required_evidence_paths)
        missing = sorted(required - observed)
        actual = f"{len(required) - len(missing)}/{len(required)}"
        detail = f"Missing required paths: {', '.join(missing) or 'none'}."
        if not required:
            return _info("required_evidence_paths", "Required evidence paths", "not configured", "informational")
        return _metric(
            "required_evidence_paths",
            "Required evidence paths",
            not missing,
            actual,
            "all configured paths observed",
            detail,
        )

    @staticmethod
    def _runtime_status(report: TakeoverReport, expected: EvaluationExpectations) -> EvaluationMetric:
        actual = report.runtime.status.value if report.runtime else "MISSING"
        target = expected.expected_runtime_status.value
        return _metric("runtime_status", "Runtime verification status", actual == target, actual, target)

    @staticmethod
    def _repository_unchanged(report: TakeoverReport, expected: EvaluationExpectations) -> EvaluationMetric:
        changed = report.runtime.repository_changed if report.runtime else None
        actual = "unknown" if changed is None else str(changed).lower()
        if not expected.require_unchanged_repository:
            return _info("repository_unchanged", "Repository remained unchanged", actual, "informational")
        return _metric(
            "repository_unchanged",
            "Repository remained unchanged",
            changed is False,
            actual,
            "false",
        )

    @staticmethod
    def _model_failures(
        model_calls: list[ModelCallSummary],
        expected: EvaluationExpectations,
    ) -> EvaluationMetric:
        if not model_calls:
            return _info("model_failures", "Model transport failures", "not observed", "informational")
        failures = sum(item.failures for item in model_calls)
        calls = sum(item.calls for item in model_calls)
        target = expected.maximum_model_failures
        return _metric(
            "model_failures",
            "Model transport failures",
            failures <= target,
            f"{failures} failures / {calls} calls",
            f"<= {target} failures",
            "Structured-output validation is reported by the architecture and learning status metrics.",
        )

    @staticmethod
    def _stage_trace(report: TakeoverReport) -> EvaluationMetric:
        completed = sum(item.status == StageStatus.COMPLETED for item in report.steps)
        failed = sum(item.status == StageStatus.FAILED for item in report.steps)
        return _info(
            "stage_trace",
            "Workflow stage trace",
            f"{completed} completed, {failed} failed",
            "informational",
        )


def load_evaluation_case(path: str | Path) -> EvaluationCase:
    source = Path(path).expanduser().resolve()
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvaluationCaseError(f"could not read evaluation case: {exc}") from exc
    try:
        return EvaluationCase.model_validate_json(raw)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in first["loc"])
        summary = f"{location}: {first['msg']}" if location else str(first["msg"])
        raise EvaluationCaseError(f"evaluation case is not valid VibeProof JSON: {summary}") from exc


def _metric(
    code: str,
    label: str,
    passed: bool,
    actual: str,
    expected: str,
    detail: str = "",
) -> EvaluationMetric:
    return EvaluationMetric(
        code=code,
        label=label,
        status=EvaluationMetricStatus.PASS if passed else EvaluationMetricStatus.FAIL,
        actual=actual,
        expected=expected,
        detail=detail,
    )


def _info(
    code: str,
    label: str,
    actual: str,
    expected: str,
    detail: str = "",
) -> EvaluationMetric:
    return EvaluationMetric(
        code=code,
        label=label,
        status=EvaluationMetricStatus.INFO,
        actual=actual,
        expected=expected,
        detail=detail,
    )
