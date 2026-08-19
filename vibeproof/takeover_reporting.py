from __future__ import annotations

from vibeproof.schemas import EvidenceReference, TakeoverReport


def render_takeover_report(report: TakeoverReport) -> str:
    lines = [
        f"# Repository takeover report: {report.repository_name}",
        "",
        f"- Status: `{report.status.value}`",
        f"- Snapshot: `{report.snapshot_id or 'unavailable'}`",
        "",
        "## Executive summary",
        "",
        report.summary,
        "",
        "## Repository",
        "",
    ]
    if report.repository is None:
        lines.append("Repository metadata is unavailable because scanning failed.")
    else:
        repository = report.repository
        lines.extend(
            [
                f"- Readable files: `{repository.scanned_files}`",
                f"- Languages: `{_mapping(repository.languages)}`",
                f"- Frameworks: `{', '.join(repository.frameworks) or 'none detected'}`",
                f"- Entrypoints: `{', '.join(repository.entrypoints) or 'none detected'}`",
                f"- Dependency files: `{', '.join(repository.dependency_files) or 'none detected'}`",
                f"- Test files: `{len(repository.test_files)}`",
            ]
        )

    lines.extend(["", "## Source index", ""])
    if report.source_index is None:
        lines.append("No source index was produced.")
    else:
        index = report.source_index
        lines.extend(
            [
                f"- Python files: `{index.indexed_files}`",
                f"- Symbols: `{index.symbol_count}`",
                f"- Source chunks: `{index.chunk_count}`",
                f"- Import edges: `{index.import_count}`",
            ]
        )

    lines.extend(["", "## Architecture analysis", ""])
    if report.architecture is None:
        lines.append("No architecture analysis was produced.")
    else:
        architecture = report.architecture
        references = {item.chunk_id: item for item in architecture.evidence}
        lines.extend(
            [
                f"- Agent status: `{architecture.run_status.value}`",
                f"- Citation review: `{architecture.verification_status.value}`",
                f"- Provider: `{architecture.provider}`",
                f"- Model: `{architecture.model}`",
                "",
                architecture.summary,
                "",
                "### Source-supported claims",
                "",
            ]
        )
        if architecture.claims:
            for claim in architecture.claims:
                citations = ", ".join(
                    _reference(references.get(chunk_id), chunk_id) for chunk_id in claim.evidence_ids
                )
                lines.append(f"- `{claim.status.value}` {claim.claim} - {citations}")
        else:
            lines.append("- None accepted.")
        lines.extend(["", "### Rejected claims", ""])
        if architecture.rejected_claims:
            for claim in architecture.rejected_claims:
                reason = claim.rejection_reason or "no reason supplied"
                lines.append(f"- `{claim.status.value}` {claim.claim} - {reason}")
        else:
            lines.append("- None.")

    lines.extend(["", "## Recommended learning path", ""])
    if report.learning_plan is None:
        lines.append("No source-grounded learning plan was produced.")
    else:
        learning = report.learning_plan
        learning_references = {item.chunk_id: item for item in learning.evidence}
        lines.extend(
            [
                f"- Status: `{learning.status.value}`",
                f"- Provider: `{learning.provider}`",
                f"- Model: `{learning.model}`",
                "",
                learning.summary,
                "",
            ]
        )
        for unit in learning.units:
            citations = ", ".join(
                _reference(learning_references.get(chunk_id), chunk_id) for chunk_id in unit.evidence_ids
            )
            lines.extend(
                [
                    f"### {unit.sequence}. {unit.title}",
                    "",
                    f"Objective: {unit.objective}",
                    "",
                    f"Why it matters: {unit.why_it_matters}",
                    "",
                    f"Exercise: {unit.exercise}",
                    "",
                    f"Evidence: {citations}",
                    "",
                ]
            )

        lines.extend(["## Source-grounded quiz", ""])
        if learning.questions:
            for question in learning.questions:
                citations = ", ".join(
                    _reference(learning_references.get(chunk_id), chunk_id)
                    for chunk_id in question.evidence_ids
                )
                lines.extend(
                    [
                        f"### {question.question_id} (`{question.difficulty.value}`)",
                        "",
                        question.prompt,
                        "",
                        f"Learning unit: `{question.unit_sequence}`  ",
                        f"Evidence: {citations}  ",
                        f"Evaluation focus: {'; '.join(question.evaluation_points)}",
                        "",
                    ]
                )
        else:
            lines.append("- No questions were accepted.")

        lines.extend(["## Rejected learning items", ""])
        lines.extend(f"- {item}" for item in learning.rejected_items)
        if not learning.rejected_items:
            lines.append("- None.")

    lines.extend(["", "## Runtime verification", ""])
    if report.runtime is None:
        lines.append("No runtime plan or evidence was produced.")
    else:
        runtime = report.runtime
        lines.extend(
            [
                f"- Status: `{runtime.status.value}`",
                f"- Executed: `{str(runtime.executed).lower()}`",
                f"- Check: `{runtime.plan.check.value}`",
                f"- Command: `{' '.join(runtime.plan.command)}`",
                f"- Interpreter: `{runtime.plan.interpreter_source.value}`",
            ]
        )
        if runtime.evidence:
            evidence = runtime.evidence
            lines.extend(
                [
                    f"- Exit code: `{evidence.exit_code}`",
                    f"- Duration: `{evidence.duration_ms} ms`",
                    f"- Output truncated: `{str(evidence.output_truncated).lower()}`",
                    "",
                    "### stdout",
                    "",
                    "```text",
                    evidence.stdout_excerpt.rstrip(),
                    "```",
                    "",
                    "### stderr",
                    "",
                    "```text",
                    evidence.stderr_excerpt.rstrip(),
                    "```",
                ]
            )

    lines.extend(["", "## Unresolved questions", ""])
    unresolved = report.architecture.unresolved_questions if report.architecture else []
    lines.extend(f"- {question}" for question in unresolved)
    if not unresolved:
        lines.append("- None recorded.")

    lines.extend(["", "## Workflow trace", ""])
    for step in report.steps:
        error = f" Error: {step.error}" if step.error else ""
        lines.append(
            f"- Step {step.step}: `{step.stage.value}` / `{step.status.value}` / `{step.duration_ms} ms` - "
            f"{step.summary}{error}"
        )

    lines.extend(["", "## Warnings and limitations", ""])
    lines.extend(f"- {warning}" for warning in report.warnings)
    if not report.warnings:
        lines.append("- None.")
    return "\n".join(lines).rstrip() + "\n"


def _mapping(values: dict[str, int]) -> str:
    return ", ".join(f"{key}: {value}" for key, value in values.items()) or "none detected"


def _reference(reference: EvidenceReference | None, chunk_id: str) -> str:
    if reference is None:
        return f"unresolved `{chunk_id}`"
    return f"`{reference.path}:{reference.start_line}-{reference.end_line}`"
