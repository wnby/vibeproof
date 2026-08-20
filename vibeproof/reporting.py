"""把架构分析结果渲染为便于人工阅读的 Markdown。

报告会展示分析状态、源码支持的结论、被拒绝的结论、文件行号引用、未解决问题、Agent 轨迹和限制，
作为 JSON 机器产物之外的可审阅视图。
"""

from __future__ import annotations

from vibeproof.schemas import ArchitectureReport, EvidenceReference


def render_architecture_report(report: ArchitectureReport) -> str:
    references = {item.chunk_id: item for item in report.evidence}
    lines = [
        f"# Architecture report: {report.repository_name}",
        "",
        f"- Snapshot: `{report.snapshot_id}`",
        f"- Run status: `{report.run_status.value}`",
        f"- Verification status: `{report.verification_status.value}`",
        f"- Provider: `{report.provider}`",
        f"- Model: `{report.model}`",
        "",
        "## Summary",
        "",
        report.summary,
        "",
        "## Source-supported claims",
        "",
    ]
    if report.claims:
        for index, claim in enumerate(report.claims, start=1):
            lines.extend(
                [
                    f"### {index}. {claim.claim}",
                    "",
                    f"Type: `{claim.claim_type.value}`  ",
                    f"Status: `{claim.status.value}`  ",
                    f"Model confidence: `{claim.confidence:.2f}`",
                    "",
                    "Evidence:",
                    "",
                ]
            )
            for chunk_id in claim.evidence_ids:
                reference = references.get(chunk_id)
                lines.append(f"- {_format_reference(reference, chunk_id)}")
            lines.append("")
    else:
        lines.extend(["No source-supported claims were accepted.", ""])

    lines.extend(["## Rejected claims", ""])
    if report.rejected_claims:
        for claim in report.rejected_claims:
            lines.append(f"- `{claim.status.value}` {claim.claim} — {claim.rejection_reason or 'no reason supplied'}")
    else:
        lines.append("No claims were rejected.")

    lines.extend(["", "## Unresolved questions", ""])
    if report.unresolved_questions:
        lines.extend(f"- {question}" for question in report.unresolved_questions)
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Agent trace", ""])
    for step in report.trace:
        detail = f" query=`{step.query}`" if step.query else ""
        result = f" evidence={len(step.returned_evidence_ids)}" if step.returned_evidence_ids else ""
        error = f" error={step.error}" if step.error else ""
        lines.append(f"- Step {step.step}: `{step.action}`{detail}{result}{error}")

    lines.extend(["", "## Warnings", ""])
    if report.warnings:
        lines.extend(f"- {warning}" for warning in report.warnings)
    else:
        lines.append("- None.")
    return "\n".join(lines).rstrip() + "\n"


def _format_reference(reference: EvidenceReference | None, chunk_id: str) -> str:
    if reference is None:
        return f"unresolved evidence `{chunk_id}`"
    symbol = f" `{reference.symbol}`" if reference.symbol else ""
    return f"`{reference.path}:{reference.start_line}-{reference.end_line}`{symbol} (`{reference.chunk_id}`)"
