"""把运行验证计划和执行证据渲染为 Markdown。

输出包含实际命令、解释器来源、状态、耗时、退出码和受限的标准输出/错误输出，使“项目是否跑过”
能够由可复查的运行证据支撑。
"""

from __future__ import annotations

from vibeproof.core.models import RuntimeVerificationReport


def render_runtime_report(report: RuntimeVerificationReport) -> str:
    """把命令计划、执行输出和仓库变化证据渲染为 Markdown。"""
    plan = report.plan
    lines = [
        f"# Runtime verification: {report.repository_name}",
        "",
        f"- Status: `{report.status.value}`",
        f"- Executed: `{str(report.executed).lower()}`",
        f"- Check: `{plan.check.value}`",
        f"- Command: `{' '.join(plan.command)}`",
        f"- Interpreter: `{plan.interpreter_source.value}`",
        f"- Before snapshot: `{report.before_snapshot_id}`",
    ]
    if report.after_snapshot_id:
        lines.append(f"- After snapshot: `{report.after_snapshot_id}`")
    lines.extend(["", "## Evidence", ""])
    if report.evidence is None:
        lines.append("No command was executed. This is a reviewable plan.")
    else:
        evidence = report.evidence
        lines.extend(
            [
                f"- Command status: `{evidence.status.value}`",
                f"- Exit code: `{evidence.exit_code}`",
                f"- Duration: `{evidence.duration_ms} ms`",
                f"- Environment variables scrubbed: `{evidence.scrubbed_environment_variables}`",
                f"- Output truncated: `{str(evidence.output_truncated).lower()}`",
            ]
        )
        if evidence.error:
            lines.extend(["", f"Error: {evidence.error}"])
        lines.extend(["", "### stdout", "", "```text", evidence.stdout_excerpt.rstrip(), "```"])
        lines.extend(["", "### stderr", "", "```text", evidence.stderr_excerpt.rstrip(), "```"])
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in report.warnings)
    if not report.warnings:
        lines.append("- None.")
    return "\n".join(lines).rstrip() + "\n"
