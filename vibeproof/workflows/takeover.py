"""编排一条完整且可部分失败的仓库接管工作流。

``TakeoverCoordinator`` 依次组织扫描、索引、架构分析、学习计划和运行验证，记录每个阶段的状态与耗时；
后续阶段失败时会尽量保留已经获得的可信产物，而不是丢弃整次结果。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from vibeproof.agents.analyst import AnalystPolicy, RepositoryAnalystAgent
from vibeproof.agents.tutor import RepositoryTutorAgent, TutorPolicy
from vibeproof.core.models import (
    AgentRunStatus,
    ArchitectureReport,
    LearningPlan,
    LearningPlanStatus,
    RepositoryManifest,
    RepositorySummary,
    RuntimeCheck,
    RuntimeStatus,
    RuntimeVerificationReport,
    SourceIndexSummary,
    StageStatus,
    TakeoverReport,
    TakeoverStage,
    TakeoverStatus,
    TakeoverStep,
)
from vibeproof.llm.client import MockTutorModelClient, ModelClient, ModelClientError
from vibeproof.repository.index import IndexPolicy, PythonSourceIndexer
from vibeproof.repository.scanner import RepositoryScanner, ScanPolicy
from vibeproof.repository.store import EvidenceStore, IndexNotFoundError
from vibeproof.runtime.verifier import RuntimePolicy, RuntimeVerifier

EXPECTED_STAGE_ERRORS = (IndexNotFoundError, ModelClientError, OSError, sqlite3.Error, ValueError)


@dataclass(frozen=True)
class TakeoverPolicy:
    scan_policy: ScanPolicy = ScanPolicy()
    index_policy: IndexPolicy = IndexPolicy()
    analyst_policy: AnalystPolicy = AnalystPolicy()
    tutor_policy: TutorPolicy = TutorPolicy()
    runtime_policy: RuntimePolicy = RuntimePolicy()
    runtime_check: RuntimeCheck = RuntimeCheck.PYTEST
    execute_runtime: bool = False
    python_executable: str | Path | None = None


class TakeoverCoordinator:
    """Compose existing evidence services into one repository takeover workflow."""

    def __init__(
        self,
        store: EvidenceStore,
        model: ModelClient,
        policy: TakeoverPolicy | None = None,
        tutor_model: ModelClient | None = None,
    ):
        self.store = store
        self.model = model
        self.policy = policy or TakeoverPolicy()
        self.scanner = RepositoryScanner(self.policy.scan_policy)
        self.indexer = PythonSourceIndexer(self.policy.index_policy)
        self.analyst = RepositoryAnalystAgent(self.store, self.model, self.policy.analyst_policy)
        resolved_tutor_model = tutor_model
        if resolved_tutor_model is None:
            resolved_tutor_model = MockTutorModelClient() if model.provider == "mock" else model
        self.tutor = RepositoryTutorAgent(self.store, resolved_tutor_model, self.policy.tutor_policy)
        self.verifier = RuntimeVerifier(self.policy.runtime_policy)

    def run(self, root: str | Path) -> TakeoverReport:
        repository_name = Path(root).expanduser().name or str(root)
        steps: list[TakeoverStep] = []
        warnings: list[str] = []

        manifest, error = self._scan(root, steps)
        if manifest is None:
            warnings.append(error or "Repository scan failed.")
            return self._failed_report(repository_name, steps, warnings)

        repository_name = manifest.repository_name
        warnings.extend(manifest.warnings)
        repository = _repository_summary(manifest)

        source_index, error = self._index(root, manifest, steps)
        if source_index is None:
            warnings.append(error or "Source indexing failed.")
            return self._failed_report(
                repository_name,
                steps,
                warnings,
                snapshot_id=manifest.snapshot_id,
                repository=repository,
            )
        warnings.extend(source_index.warnings)

        architecture, analysis_error = self._analyze(manifest, steps)
        if architecture is not None:
            warnings.extend(architecture.warnings)
        elif analysis_error:
            warnings.append(analysis_error)

        learning_plan = self._learn(manifest, architecture, steps)
        if learning_plan is not None:
            warnings.extend(learning_plan.warnings)

        runtime, runtime_error = self._runtime(root, steps)
        if runtime is not None:
            warnings.extend(runtime.warnings)
        elif runtime_error:
            warnings.append(runtime_error)

        status = _takeover_status(manifest, architecture, learning_plan, runtime)
        if runtime is not None and runtime.before_snapshot_id != manifest.snapshot_id:
            status = TakeoverStatus.SNAPSHOT_CHANGED
            warnings.append("Runtime verification started from a different snapshot than source analysis.")

        steps.append(
            TakeoverStep(
                step=len(steps) + 1,
                stage=TakeoverStage.REPORT,
                status=StageStatus.COMPLETED,
                summary="Composed the available manifest, source, analysis, and runtime artifacts.",
                duration_ms=0,
            )
        )
        return TakeoverReport(
            repository_name=repository_name,
            snapshot_id=manifest.snapshot_id,
            status=status,
            summary=_report_summary(status, runtime),
            repository=repository,
            source_index=source_index,
            architecture=architecture,
            learning_plan=learning_plan,
            runtime=runtime,
            steps=steps,
            warnings=_unique(warnings),
        )

    def _scan(self, root: str | Path, steps: list[TakeoverStep]) -> tuple[RepositoryManifest | None, str | None]:
        started = monotonic()
        try:
            manifest = self.scanner.scan(root)
        except EXPECTED_STAGE_ERRORS as exc:
            error = str(exc)
            steps.append(_failed_step(steps, TakeoverStage.SCAN, started, error))
            return None, error
        steps.append(
            _completed_step(
                steps,
                TakeoverStage.SCAN,
                started,
                f"Scanned {manifest.statistics.indexed_files} readable files.",
            )
        )
        return manifest, None

    def _index(
        self,
        root: str | Path,
        manifest: RepositoryManifest,
        steps: list[TakeoverStep],
    ) -> tuple[SourceIndexSummary | None, str | None]:
        started = monotonic()
        try:
            indexed = self.indexer.build(root, manifest)
            summary = self.store.replace_snapshot(manifest.repository_name, manifest.snapshot_id, indexed)
        except EXPECTED_STAGE_ERRORS as exc:
            error = str(exc)
            steps.append(_failed_step(steps, TakeoverStage.INDEX, started, error))
            return None, error
        steps.append(
            _completed_step(
                steps,
                TakeoverStage.INDEX,
                started,
                f"Indexed {summary.indexed_files} Python files into {summary.chunk_count} source chunks.",
            )
        )
        return summary, None

    def _analyze(
        self,
        manifest: RepositoryManifest,
        steps: list[TakeoverStep],
    ) -> tuple[ArchitectureReport | None, str | None]:
        started = monotonic()
        try:
            report = self.analyst.run(manifest)
        except EXPECTED_STAGE_ERRORS as exc:
            error = str(exc)
            steps.append(_failed_step(steps, TakeoverStage.ANALYZE, started, error))
            return None, error
        stage_status = StageStatus.COMPLETED if report.run_status == AgentRunStatus.COMPLETED else StageStatus.FAILED
        steps.append(
            TakeoverStep(
                step=len(steps) + 1,
                stage=TakeoverStage.ANALYZE,
                status=stage_status,
                summary=(
                    f"Accepted {len(report.claims)} claims and rejected {len(report.rejected_claims)} claims."
                    if stage_status == StageStatus.COMPLETED
                    else report.summary
                ),
                duration_ms=_elapsed_ms(started),
                error=report.warnings[0] if stage_status == StageStatus.FAILED and report.warnings else None,
            )
        )
        return report, None

    def _learn(
        self,
        manifest: RepositoryManifest,
        architecture: ArchitectureReport | None,
        steps: list[TakeoverStep],
    ) -> LearningPlan | None:
        started = monotonic()
        if architecture is None or architecture.run_status != AgentRunStatus.COMPLETED:
            error = "Learning plan requires a completed architecture analysis."
            steps.append(_failed_step(steps, TakeoverStage.LEARNING_PLAN, started, error))
            return None
        try:
            plan = self.tutor.run(manifest, architecture)
        except EXPECTED_STAGE_ERRORS as exc:
            error = str(exc)
            steps.append(_failed_step(steps, TakeoverStage.LEARNING_PLAN, started, error))
            return None
        status = StageStatus.COMPLETED if plan.status == LearningPlanStatus.SOURCE_GROUNDED else StageStatus.FAILED
        error = None
        if status == StageStatus.FAILED:
            error = plan.rejected_items[0] if plan.rejected_items else plan.warnings[0] if plan.warnings else None
        steps.append(
            TakeoverStep(
                step=len(steps) + 1,
                stage=TakeoverStage.LEARNING_PLAN,
                status=status,
                summary=(
                    f"Created {len(plan.units)} learning units and "
                    f"{len(plan.questions)} source-grounded questions."
                ),
                duration_ms=_elapsed_ms(started),
                error=error,
            )
        )
        return plan

    def _runtime(
        self,
        root: str | Path,
        steps: list[TakeoverStep],
    ) -> tuple[RuntimeVerificationReport | None, str | None]:
        started = monotonic()
        stage = TakeoverStage.RUNTIME_EXECUTION if self.policy.execute_runtime else TakeoverStage.RUNTIME_PLAN
        try:
            report = self.verifier.verify(
                root,
                check=self.policy.runtime_check,
                execute=self.policy.execute_runtime,
                python_executable=self.policy.python_executable,
            )
        except EXPECTED_STAGE_ERRORS as exc:
            error = str(exc)
            steps.append(_failed_step(steps, stage, started, error))
            return None, error
        success_statuses = {RuntimeStatus.PLANNED, RuntimeStatus.PASSED}
        status = StageStatus.COMPLETED if report.status in success_statuses else StageStatus.FAILED
        steps.append(
            TakeoverStep(
                step=len(steps) + 1,
                stage=stage,
                status=status,
                summary=f"Runtime check finished with status {report.status.value}.",
                duration_ms=_elapsed_ms(started),
                error=_runtime_error(report) if status == StageStatus.FAILED else None,
            )
        )
        return report, None

    @staticmethod
    def _failed_report(
        repository_name: str,
        steps: list[TakeoverStep],
        warnings: list[str],
        *,
        snapshot_id: str | None = None,
        repository: RepositorySummary | None = None,
    ) -> TakeoverReport:
        steps.append(
            TakeoverStep(
                step=len(steps) + 1,
                stage=TakeoverStage.REPORT,
                status=StageStatus.COMPLETED,
                summary="Composed a failure report from the completed workflow stages.",
                duration_ms=0,
            )
        )
        return TakeoverReport(
            repository_name=repository_name,
            snapshot_id=snapshot_id,
            status=TakeoverStatus.FAILED,
            summary="Repository takeover stopped before source analysis could complete.",
            repository=repository,
            steps=steps,
            warnings=_unique(warnings),
        )


def _repository_summary(manifest: RepositoryManifest) -> RepositorySummary:
    return RepositorySummary(
        repository_name=manifest.repository_name,
        snapshot_id=manifest.snapshot_id,
        languages=manifest.languages,
        frameworks=manifest.frameworks,
        entrypoints=manifest.entrypoints,
        dependency_files=manifest.dependency_files,
        test_files=manifest.test_files,
        scanned_files=manifest.statistics.indexed_files,
    )


def _takeover_status(
    manifest: RepositoryManifest,
    architecture: ArchitectureReport | None,
    learning_plan: LearningPlan | None,
    runtime: RuntimeVerificationReport | None,
) -> TakeoverStatus:
    if runtime is not None and (
        runtime.status == RuntimeStatus.SNAPSHOT_CHANGED
        or runtime.after_snapshot_id not in {None, manifest.snapshot_id}
    ):
        return TakeoverStatus.SNAPSHOT_CHANGED
    if architecture is None or architecture.run_status != AgentRunStatus.COMPLETED:
        return TakeoverStatus.PARTIAL
    if learning_plan is None or learning_plan.status != LearningPlanStatus.SOURCE_GROUNDED:
        return TakeoverStatus.PARTIAL
    if runtime is None or runtime.status not in {RuntimeStatus.PLANNED, RuntimeStatus.PASSED}:
        return TakeoverStatus.PARTIAL
    return TakeoverStatus.COMPLETED


def _report_summary(status: TakeoverStatus, runtime: RuntimeVerificationReport | None) -> str:
    if status == TakeoverStatus.COMPLETED:
        runtime_kind = "runtime evidence" if runtime and runtime.executed else "a reviewable runtime plan"
        return (
            "Repository takeover completed with architecture evidence, a grounded learning plan, "
            f"and {runtime_kind}."
        )
    if status == TakeoverStatus.SNAPSHOT_CHANGED:
        return "Repository content changed during takeover; review the recorded before and after snapshots."
    return "Repository takeover produced partial evidence; review failed workflow stages and warnings."


def _runtime_error(report: RuntimeVerificationReport) -> str | None:
    if report.evidence and report.evidence.error:
        return report.evidence.error
    if report.evidence and report.evidence.exit_code is not None:
        return f"Runtime command exited with code {report.evidence.exit_code}."
    return report.warnings[0] if report.warnings else None


def _completed_step(
    steps: list[TakeoverStep],
    stage: TakeoverStage,
    started: float,
    summary: str,
) -> TakeoverStep:
    return TakeoverStep(
        step=len(steps) + 1,
        stage=stage,
        status=StageStatus.COMPLETED,
        summary=summary,
        duration_ms=_elapsed_ms(started),
    )


def _failed_step(
    steps: list[TakeoverStep],
    stage: TakeoverStage,
    started: float,
    error: str,
) -> TakeoverStep:
    return TakeoverStep(
        step=len(steps) + 1,
        stage=stage,
        status=StageStatus.FAILED,
        summary=f"{stage.value.replace('_', ' ').title()} failed.",
        duration_ms=_elapsed_ms(started),
        error=error,
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1_000))


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
