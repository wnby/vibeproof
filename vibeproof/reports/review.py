"""把答案评审结果渲染为 Markdown 学习报告。

本模块汇总完成率、语义评审数量、掌握率和推荐复习单元，并逐题展示状态、分数、反馈、知识缺口及
对应源码行号，同时明确 Mock 结构校验等评审限制。
"""

from __future__ import annotations

from vibeproof.core.models import AnswerReviewReport, EvidenceReference, QuizQuestionDraft, TakeoverReport


def render_answer_review(report: AnswerReviewReport, takeover: TakeoverReport) -> str:
    questions = {
        item.question_id: item
        for item in (takeover.learning_plan.questions if takeover.learning_plan else [])
    }
    references = {item.chunk_id: item for item in report.evidence}
    progress = report.progress
    lines = [
        f"# Learning review: {report.repository_name}",
        "",
        f"- Status: `{report.status.value}`",
        f"- Review mode: `{report.mode.value}`",
        f"- Provider: `{report.provider}`",
        f"- Model: `{report.model}`",
        f"- Snapshot: `{report.snapshot_id}`",
        "",
        "## Progress",
        "",
        f"- Answered: `{progress.answered_questions}/{progress.total_questions}` "
        f"(`{progress.completion_percent:.1f}%`)",
        f"- Semantically assessed: `{progress.assessed_questions}/{progress.total_questions}`",
        f"- Passed: `{progress.passed_questions}`",
        f"- Needs improvement: `{progress.needs_improvement}`",
        f"- Not assessed: `{progress.not_assessed}`",
        f"- Rejected assessments: `{progress.rejected}`",
        f"- Evidence-backed mastery: `{progress.mastery_percent:.1f}%`",
        f"- Recommended next units: `{', '.join(map(str, progress.recommended_next_units)) or 'none'}`",
        "",
        "## Answer assessments",
        "",
    ]
    for assessment in report.assessments:
        question = questions.get(assessment.question_id)
        lines.extend(_assessment_lines(assessment, question, references))

    lines.extend(["## Warnings and limitations", ""])
    lines.extend(f"- {warning}" for warning in report.warnings)
    if not report.warnings:
        lines.append("- None.")
    return "\n".join(lines).rstrip() + "\n"


def _assessment_lines(assessment, question: QuizQuestionDraft | None, references: dict[str, EvidenceReference]):
    prompt = question.prompt if question else "Question metadata unavailable."
    score = str(assessment.score) if assessment.score is not None else "not scored"
    citations = ", ".join(_reference(references.get(item), item) for item in assessment.evidence_ids)
    lines = [
        f"### {assessment.question_id} — `{assessment.status.value}`",
        "",
        prompt,
        "",
        f"- Unit: `{assessment.unit_sequence}`",
        f"- Score: `{score}`",
        f"- Evidence: {citations or 'none'}",
        "",
        assessment.feedback,
        "",
    ]
    if assessment.strengths:
        lines.extend(["Strengths:", "", *(f"- {item}" for item in assessment.strengths), ""])
    if assessment.gaps:
        lines.extend(["Gaps to revisit:", "", *(f"- {item}" for item in assessment.gaps), ""])
    return lines


def _reference(reference: EvidenceReference | None, chunk_id: str) -> str:
    if reference is None:
        return f"unresolved `{chunk_id}`"
    return f"`{reference.path}:{reference.start_line}-{reference.end_line}`"
