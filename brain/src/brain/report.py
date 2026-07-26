"""Report validation and rendering (API.md section 3).

Every claim must cite a chunk_id that resolves in the chunk store; dangling
citations are stripped with a warning rather than failing the run.
"""

import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .agent.protocol import FENCE_RE


class ReportError(Exception):
    """str(e) is fed back to the model as validation errors on retry."""


class EvidenceItem(BaseModel):
    chunk_id: str
    why: str


class RuledOutItem(BaseModel):
    hypothesis: str
    why: str
    chunk_id: str | None = None


class ActionStep(BaseModel):
    step: int
    action: str
    command: str | None = None
    risk: Literal["low", "medium", "high"] = "low"


class Report(BaseModel):
    root_cause: str
    confidence: Literal["high", "medium", "low"]
    affected_machines: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    ruled_out: list[RuledOutItem] = Field(default_factory=list)
    action_plan: list[ActionStep] = Field(default_factory=list)
    proposed_fix_script: str | None = None


def parse_report(text: str, known_chunk_ids: set[str]) -> tuple[Report, list[str]]:
    """Parse + validate; strip citations that do not resolve. Returns (report, warnings)."""
    stripped = FENCE_RE.sub("", text.strip()).strip()
    # the conclude turn may stream prose before the JSON object; take the outermost object
    first = stripped.find("{")
    last = stripped.rfind("}")
    if first == -1 or last <= first:
        raise ReportError("no JSON object found in output")
    try:
        raw = json.loads(stripped[first : last + 1])
    except json.JSONDecodeError as e:
        raise ReportError(f"report is not valid JSON: {e}") from e
    try:
        report = Report.model_validate(raw)
    except ValidationError as e:
        raise ReportError(f"report schema violation: {e.errors(include_url=False)}") from e

    warnings: list[str] = []
    kept = []
    for item in report.evidence:
        if item.chunk_id in known_chunk_ids:
            kept.append(item)
        else:
            warnings.append(f"stripped dangling citation {item.chunk_id}")
    report.evidence = kept
    for item in report.ruled_out:
        if item.chunk_id is not None and item.chunk_id not in known_chunk_ids:
            warnings.append(f"stripped dangling citation {item.chunk_id}")
            item.chunk_id = None
    return report, warnings


def render_markdown(report: Report, *, run_id: str, elapsed_s: float, bundle_ids: list[str], query_trail: list[str]) -> str:
    lines = [
        f"# Diagnosis - {run_id}",
        "",
        f"Elapsed: {elapsed_s:.1f} s | Confidence: {report.confidence} | Bundles: {', '.join(bundle_ids)}",
        "",
        "## Root cause",
        "",
        report.root_cause,
        "",
    ]
    if report.affected_machines:
        lines += [f"Affected machines: {', '.join(report.affected_machines)}", ""]
    if report.evidence:
        lines += ["## Evidence", ""]
        for item in report.evidence:
            lines.append(f"- `{item.chunk_id}` - {item.why}")
        lines.append("")
    if report.ruled_out:
        lines += ["## Ruled out", ""]
        for item in report.ruled_out:
            cite = f" (`{item.chunk_id}`)" if item.chunk_id else ""
            lines.append(f"- {item.hypothesis} - {item.why}{cite}")
        lines.append("")
    if report.action_plan:
        lines += ["## Action plan", ""]
        for step in report.action_plan:
            cmd = f" - `{step.command}`" if step.command else ""
            lines.append(f"{step.step}. {step.action} (risk: {step.risk}){cmd}")
        lines.append("")
    if report.proposed_fix_script:
        lines += [
            "## Proposed fix script (advisory - never executed by the Brain, see ADR-0010)",
            "",
            "```bash",
            report.proposed_fix_script.rstrip("\n"),
            "```",
            "",
        ]
    if query_trail:
        lines += ["## Query trail", ""]
        for entry in query_trail:
            lines.append(f"- {entry}")
        lines.append("")
    return "\n".join(lines)
