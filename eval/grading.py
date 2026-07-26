"""Automatic grading of a run's report against scenario/ground_truth.md.

Each criterion is a named predicate over the report JSON. 'required' criteria
define pass/fail (ground truth 'full marks' minus subjective wording); the
rest are bonus signals worth tracking across trials, including the near-miss
trap, which is graded as an inverted criterion (firewall as ROOT CAUSE = fail).
"""

from dataclasses import dataclass
from typing import Callable

ENV_CHUNK_PREFIX = "laptop-a:services/backend/config/backend.env"
LOG_CHUNK_PREFIXES = ("laptop-a:app_logs/backend.log", "laptop-a:services/backend/journal.txt")
MIGRATION_DOC = "db-migration-2025"


def _text_blob(report: dict) -> str:
    parts = [report.get("root_cause", ""), report.get("proposed_fix_script") or ""]
    parts += [s.get("action", "") + " " + (s.get("command") or "") for s in report.get("action_plan", [])]
    return " ".join(parts).lower()


def _evidence_ids(report: dict) -> list[str]:
    return [e.get("chunk_id", "") for e in report.get("evidence", [])]


@dataclass(frozen=True)
class Criterion:
    name: str
    required: bool
    check: Callable[[dict], bool]


CRITERIA = [
    # ---- required: ground truth "full marks" ----
    Criterion("names_db_host_var", True, lambda r: "db_host" in r.get("root_cause", "").lower()),
    Criterion("names_backend_env_file", True, lambda r: "backend.env" in r.get("root_cause", "").lower()),
    Criterion("identifies_stale_host", True, lambda r: "db.internal" in r.get("root_cause", "").lower()),
    Criterion("cites_config_line", True, lambda r: any(c.startswith(ENV_CHUNK_PREFIX) for c in _evidence_ids(r))),
    Criterion("cites_log_error", True, lambda r: any(c.startswith(p) for c in _evidence_ids(r) for p in LOG_CHUNK_PREFIXES)),
    Criterion("fix_uses_correct_host", True, lambda r: "127.0.0.1" in _text_blob(r)),
    Criterion("fix_restarts_backend", True, lambda r: "restart" in _text_blob(r)),
    # the near-miss trap: blaming the firewall as root cause is an outright fail
    Criterion("avoids_firewall_trap", True, lambda r: "firewall" not in r.get("root_cause", "").lower()),
    # ---- bonus: quality signals worth tracking ----
    Criterion("cross_machine_evidence", False, lambda r: any(c.startswith("laptop-b:") for c in _evidence_ids(r))),
    Criterion("cites_migration_doc", False, lambda r: any(MIGRATION_DOC in c for c in _evidence_ids(r))),
    Criterion("rules_out_firewall", False, lambda r: any("firewall" in x.get("hypothesis", "").lower() for x in report_ruled_out(r))),
    Criterion("confidence_high", False, lambda r: r.get("confidence") == "high"),
    Criterion("has_fix_script", False, lambda r: bool(r.get("proposed_fix_script"))),
]


def report_ruled_out(report: dict) -> list[dict]:
    return report.get("ruled_out", []) or []


def grade(report: dict | None) -> dict:
    """Returns {passed, required_failed, criteria: {name: bool}}. A missing
    report (failed run) fails every criterion."""
    results = {c.name: bool(report and _safe(c.check, report)) for c in CRITERIA}
    required_failed = [c.name for c in CRITERIA if c.required and not results[c.name]]
    return {"passed": not required_failed, "required_failed": required_failed, "criteria": results}


def _safe(check: Callable[[dict], bool], report: dict) -> bool:
    try:
        return check(report)
    except Exception:  # noqa: BLE001 - a malformed report is a failed criterion, not a crash
        return False
