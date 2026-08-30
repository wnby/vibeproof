"""在本地后台线程中执行 Web 接管，并把真实阶段和最终产物持续写入 JSON。"""

from __future__ import annotations

from pathlib import Path
from threading import Thread

from vibeproof.agents.reviewer import AnswerReviewAgent
from vibeproof.core.models import (
    LearningAttempt,
    QuizSubmission,
    TakeoverStage,
    TakeoverStatus,
    TakeoverStep,
    WebRunConfiguration,
    WebRunRecord,
    WebRunStatus,
)
from vibeproof.llm.client import ModelClient
from vibeproof.repository.run_store import RunStore
from vibeproof.repository.store import EvidenceStore
from vibeproof.workflows.takeover import TakeoverCoordinator, TakeoverPolicy


class WebRunService:
    """连接后台执行、阶段检查点、学习评审和可恢复的本地 Run 记录。"""

    def __init__(self, run_store: RunStore, evidence_store: EvidenceStore):
        self.run_store = run_store
        self.evidence_store = evidence_store

    def start(
        self,
        target: str | Path,
        configuration: WebRunConfiguration,
        analyst_model: ModelClient,
        tutor_model: ModelClient,
        policy: TakeoverPolicy,
    ) -> WebRunRecord:
        """创建可立即轮询的记录，并在守护线程中执行完整接管。"""
        record = self.run_store.create(WebRunRecord(configuration=configuration))
        Thread(
            target=self._execute,
            args=(record.run_id, Path(target), analyst_model, tutor_model, policy),
            daemon=True,
            name=f"vibeproof-{record.run_id}",
        ).start()
        return record

    def retry(
        self,
        run_id: str,
        target: str | Path,
        stage: TakeoverStage,
        analyst_model: ModelClient,
        tutor_model: ModelClient,
        policy: TakeoverPolicy,
    ) -> WebRunRecord:
        """从已保存报告定向重跑失败的 Tutor 或 Runtime 阶段。"""
        record = self.run_store.load(run_id)
        if record.status in {WebRunStatus.PENDING, WebRunStatus.RUNNING}:
            raise ValueError("run is already in progress")
        if record.report is None:
            raise ValueError("run has no checkpoint report to retry")
        running = self.run_store.save(
            record.model_copy(update={"status": WebRunStatus.RUNNING, "active_stage": stage, "error": None})
        )
        Thread(
            target=self._retry,
            args=(run_id, Path(target), stage, analyst_model, tutor_model, policy),
            daemon=True,
            name=f"vibeproof-retry-{run_id}",
        ).start()
        return running

    def review(
        self,
        run_id: str,
        submission: QuizSubmission,
        model: ModelClient,
    ) -> LearningAttempt:
        """评审一轮答案并追加保存，旧的学习尝试保持不变。"""
        record = self.run_store.load(run_id)
        if record.status in {WebRunStatus.PENDING, WebRunStatus.RUNNING}:
            raise ValueError("run must finish before answers can be reviewed")
        if record.report is None:
            raise ValueError("run has no takeover report to review")
        review = AnswerReviewAgent(self.evidence_store, model).run(record.report, submission)
        attempt = LearningAttempt(submission=submission, review=review)
        self.run_store.save(record.model_copy(update={"attempts": [*record.attempts, attempt]}))
        return attempt

    def _execute(
        self,
        run_id: str,
        target: Path,
        analyst_model: ModelClient,
        tutor_model: ModelClient,
        policy: TakeoverPolicy,
    ) -> None:
        record = self.run_store.load(run_id)
        self.run_store.save(record.model_copy(update={"status": WebRunStatus.RUNNING, "error": None}))
        coordinator = TakeoverCoordinator(
            self.evidence_store,
            analyst_model,
            policy,
            tutor_model,
            on_step=lambda step: self._save_step(run_id, step),
        )
        try:
            report = coordinator.run(target)
            current = self.run_store.load(run_id)
            self.run_store.save(
                current.model_copy(
                    update={
                        "status": _web_status(report.status),
                        "active_stage": None,
                        "steps": report.steps,
                        "report": report,
                        "error": None,
                    }
                )
            )
        except Exception as exc:  # background boundary: persist unexpected failures for the UI
            self._save_failure(run_id, exc)

    def _retry(
        self,
        run_id: str,
        target: Path,
        stage: TakeoverStage,
        analyst_model: ModelClient,
        tutor_model: ModelClient,
        policy: TakeoverPolicy,
    ) -> None:
        record = self.run_store.load(run_id)
        coordinator = TakeoverCoordinator(
            self.evidence_store,
            analyst_model,
            policy,
            tutor_model,
            on_step=lambda step: self._save_step(run_id, step),
        )
        try:
            if record.report is None:
                raise ValueError("run has no checkpoint report to retry")
            report = coordinator.retry_stage(target, record.report, stage)
            current = self.run_store.load(run_id)
            self.run_store.save(
                current.model_copy(
                    update={
                        "status": _web_status(report.status),
                        "active_stage": None,
                        "steps": report.steps,
                        "report": report,
                        "error": None,
                    }
                )
            )
        except Exception as exc:  # background boundary: persist unexpected failures for the UI
            self._save_failure(run_id, exc)

    def _save_step(self, run_id: str, step: TakeoverStep) -> None:
        record = self.run_store.load(run_id)
        steps = list(record.steps)
        if not steps or steps[-1] != step:
            steps.append(step)
        self.run_store.save(record.model_copy(update={"active_stage": step.stage, "steps": steps}))

    def _save_failure(self, run_id: str, exc: Exception) -> None:
        record = self.run_store.load(run_id)
        self.run_store.save(
            record.model_copy(update={"status": WebRunStatus.FAILED, "active_stage": None, "error": str(exc)})
        )


def _web_status(status: TakeoverStatus) -> WebRunStatus:
    if status == TakeoverStatus.COMPLETED:
        return WebRunStatus.COMPLETED
    if status in {TakeoverStatus.PARTIAL, TakeoverStatus.SNAPSHOT_CHANGED}:
        return WebRunStatus.PARTIAL
    return WebRunStatus.FAILED
