"""将确定性 Agent Eval 结果渲染为 Markdown 报告。

报告展示评估用例、模型信息、耗时、通过/失败指标以及原始接管状态，并明确区分证据来源验证与模型
语义正确性，便于在 GitHub、CI 和面试材料中复查结果。
"""

from __future__ import annotations

from vibeproof.core.models import EvaluationReport


def render_evaluation_report(report: EvaluationReport) -> str:
    architecture = report.takeover.architecture
    learning = report.takeover.learning_plan
    lines = [
        f"# Agent evaluation: {report.repository_name}",
        "",
        f"- Status: `{report.status.value}`",
        f"- Case: `{report.case_id}` — {report.case_name}",
        f"- Provider: `{report.provider}`",
        f"- Model: `{report.model}`",
        f"- Snapshot: `{report.snapshot_id or 'unavailable'}`",
        f"- Duration: `{report.duration_ms} ms`",
        f"- Metrics: `{report.passed_metrics} passed / {report.failed_metrics} failed / "
        f"{report.info_metrics} informational`",
        "",
        "## Metrics",
        "",
        "| Status | Metric | Actual | Expected |",
        "| --- | --- | --- | --- |",
    ]
    for metric in report.metrics:
        lines.append(
            f"| `{metric.status.value}` | {metric.label} | {_cell(metric.actual)} | {_cell(metric.expected)} |"
        )
        if metric.detail:
            lines.extend(["", f"> `{metric.code}`: {metric.detail}", ""])

    lines.extend(
        [
            "",
            "## Model activity",
            "",
        ]
    )
    if report.model_calls:
        for item in report.model_calls:
            lines.append(
                f"- `{item.task}`: `{item.calls}` calls, `{item.failures}` failures, `{item.duration_ms} ms`"
            )
    else:
        lines.append("- Model-call observation was not supplied.")
    lines.extend(
        [
            "",
            "## Takeover summary",
            "",
            f"- Workflow status: `{report.takeover.status.value}`",
            f"- Accepted architecture claims: `{len(architecture.claims) if architecture else 0}`",
            f"- Rejected architecture claims: `{len(architecture.rejected_claims) if architecture else 0}`",
            f"- Learning units: `{len(learning.units) if learning else 0}`",
            f"- Quiz questions: `{len(learning.questions) if learning else 0}`",
            f"- Runtime status: `{report.takeover.runtime.status.value if report.takeover.runtime else 'MISSING'}`",
            "",
            "## Warnings and interpretation",
            "",
        ]
    )
    lines.extend(f"- {warning}" for warning in report.warnings)
    if not report.warnings:
        lines.append("- None.")
    return "\n".join(lines).rstrip() + "\n"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
