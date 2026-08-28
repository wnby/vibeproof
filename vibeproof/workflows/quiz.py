"""负责接管报告与答题文件之间的转换和文件校验。

本模块读取严格类型的 JSON 接管报告，从其中的源码题目生成带身份信息的空白答题模板，并在评审前
解析用户提交，避免手写文件格式错误悄悄进入后续流程。
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from vibeproof.core.models import AnswerSubmission, QuizSubmission, TakeoverReport


class QuizFileError(ValueError):
    pass


def load_takeover_report(path: str | Path) -> TakeoverReport:
    source = Path(path).expanduser().resolve()
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise QuizFileError(f"could not read takeover report: {exc}") from exc
    try:
        return TakeoverReport.model_validate_json(raw)
    except ValidationError as exc:
        raise QuizFileError(f"takeover report is not valid VibeProof JSON: {_validation_summary(exc)}") from exc


def load_quiz_submission(path: str | Path) -> QuizSubmission:
    source = Path(path).expanduser().resolve()
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise QuizFileError(f"could not read quiz submission: {exc}") from exc
    try:
        return QuizSubmission.model_validate_json(raw)
    except ValidationError as exc:
        raise QuizFileError(f"quiz submission is not valid VibeProof JSON: {_validation_summary(exc)}") from exc


def create_quiz_submission(report: TakeoverReport) -> QuizSubmission:
    plan = report.learning_plan
    if plan is None or not plan.questions:
        raise QuizFileError("takeover report does not contain a source-grounded quiz")
    if not report.snapshot_id or plan.snapshot_id != report.snapshot_id:
        raise QuizFileError("takeover report and learning plan snapshot IDs do not match")

    evidence_ids = {item.chunk_id for item in plan.evidence}
    question_ids: set[str] = set()
    answers: list[AnswerSubmission] = []
    for question in plan.questions:
        if question.question_id in question_ids:
            raise QuizFileError(f"takeover report contains duplicate question ID: {question.question_id}")
        question_ids.add(question.question_id)
        missing = set(question.evidence_ids) - evidence_ids
        if missing:
            raise QuizFileError(
                f"question {question.question_id} references unavailable evidence: {', '.join(sorted(missing))}"
            )
        answers.append(AnswerSubmission(question_id=question.question_id, answer=""))

    return QuizSubmission(
        report_id=report.report_id,
        plan_id=plan.plan_id,
        snapshot_id=report.snapshot_id,
        answers=answers,
    )


def write_json(path: str | Path, value: QuizSubmission) -> Path:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(value.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return destination


def _validation_summary(exc: ValidationError) -> str:
    first = exc.errors(include_url=False)[0]
    location = ".".join(str(part) for part in first["loc"])
    return f"{location}: {first['msg']}" if location else str(first["msg"])
