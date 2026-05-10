from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from farrlind_pipeline.models.schemas import StitchedTranscript, ValidationFinding, ValidationReport


def validate_transcript_placeholder(
    stitched: StitchedTranscript,
    output_dir: str | Path,
) -> ValidationReport:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    findings: list[ValidationFinding] = []
    if not stitched.chunks:
        findings.append(
            ValidationFinding(
                code="no_chunks",
                severity="error",
                message="No transcript chunks were available to validate.",
            )
        )

    for chunk in stitched.chunks:
        if not chunk.text.strip():
            findings.append(
                ValidationFinding(
                    code="empty_chunk",
                    severity="warning",
                    message=f"{chunk.chunk_id} has no transcript text.",
                    chunk_id=chunk.chunk_id,
                )
            )
        if chunk.metadata.get("placeholder"):
            findings.append(
                ValidationFinding(
                    code="placeholder_transcript",
                    severity="info",
                    message=f"{chunk.chunk_id} was produced by the placeholder transcription worker.",
                    chunk_id=chunk.chunk_id,
                )
            )

    for warning in stitched.warnings:
        findings.append(
            ValidationFinding(
                code="stitch_warning",
                severity="warning",
                message=warning,
            )
        )

    report = ValidationReport(
        session_id=stitched.session_id,
        status="needs_review" if findings else "succeeded",
        findings=findings,
        checked_at=datetime.now(timezone.utc),
    )

    (output_dir / "validation_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (output_dir / "validation_report.md").write_text(render_validation_markdown(report), encoding="utf-8")
    return report


def render_validation_markdown(report: ValidationReport) -> str:
    lines = [
        f"# Validation Report: {report.session_id}",
        "",
        f"Status: `{report.status}`",
        "",
    ]
    if not report.findings:
        lines.append("No validation findings.")
    else:
        lines.append("## Findings")
        lines.append("")
        for finding in report.findings:
            chunk = f" ({finding.chunk_id})" if finding.chunk_id else ""
            lines.append(f"- `{finding.severity}` `{finding.code}`{chunk}: {finding.message}")
    lines.append("")
    return "\n".join(lines)
