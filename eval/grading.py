"""Automatic grading of a run's report against a scenario's ground truth.

Each criterion is a named predicate over the report JSON. 'required' criteria
define pass/fail (ground truth 'full marks' minus subjective wording); the
rest are bonus signals worth tracking across trials, including the near-miss
trap, which is graded as an inverted criterion (firewall as ROOT CAUSE = fail).

Two scenarios are known:
- "fixture": the bundled test fixtures under brain/tests/fixtures/ (stale
  DB_HOST=db.internal, docs/db-migration-2025.md).
- "clinic": Cedar Hollow bundles collected from a live scenario/ deployment
  (stale DB_HOST=db-primary.cedarhollow.internal, graded per
  scenario/ground_truth.md). Clinic machine IDs come from real hostnames, so
  chunk-ID checks match on path markers rather than machine prefixes.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Scenario:
    stale_host: str
    env_chunk_marker: str  # substring of the config chunk's ID
    log_chunk_markers: tuple[str, ...]  # substrings of log/journal chunk IDs
    migration_doc: str
    fix_host: str = "127.0.0.1"


SCENARIOS = {
    "fixture": Scenario(
        stale_host="db.internal",
        env_chunk_marker="services/backend/config/backend.env",
        log_chunk_markers=("app_logs/backend.log", "services/backend/journal.txt"),
        migration_doc="db-migration-2025",
    ),
    "clinic": Scenario(
        stale_host="db-primary.cedarhollow.internal",
        env_chunk_marker="backend.env",
        log_chunk_markers=("backend.log", "journal"),
        migration_doc="records-host-migration-2026",
    ),
}


def _text_blob(report: dict) -> str:
    parts = [report.get("root_cause", ""), report.get("proposed_fix_script") or ""]
    parts += [s.get("action", "") + " " + (s.get("command") or "") for s in report.get("action_plan", [])]
    return " ".join(parts).lower()


def _evidence_ids(report: dict) -> list[str]:
    return [e.get("chunk_id", "") for e in report.get("evidence", [])]


def _machines_cited(report: dict) -> set[str]:
    return {c.split(":", 1)[0] for c in _evidence_ids(report) if ":" in c}


@dataclass(frozen=True)
class Criterion:
    name: str
    required: bool
    check: Callable[[dict], bool]


def criteria_for(s: Scenario) -> list[Criterion]:
    return [
        # ---- required: ground truth "full marks" ----
        Criterion("names_db_host_var", True, lambda r: "db_host" in r.get("root_cause", "").lower()),
        Criterion("names_backend_env_file", True, lambda r: "backend.env" in r.get("root_cause", "").lower()),
        Criterion("identifies_stale_host", True, lambda r: s.stale_host in r.get("root_cause", "").lower()),
        Criterion("cites_config_line", True, lambda r: any(s.env_chunk_marker in c for c in _evidence_ids(r))),
        Criterion("cites_log_error", True, lambda r: any(m in c for c in _evidence_ids(r) for m in s.log_chunk_markers)),
        Criterion("fix_uses_correct_host", True, lambda r: s.fix_host in _text_blob(r)),
        Criterion("fix_restarts_backend", True, lambda r: "restart" in _text_blob(r)),
        # the near-miss trap: blaming the firewall as root cause is an outright fail
        Criterion("avoids_firewall_trap", True, lambda r: "firewall" not in r.get("root_cause", "").lower()),
        # ---- bonus: quality signals worth tracking ----
        Criterion("cross_machine_evidence", False, lambda r: len(_machines_cited(r)) >= 2),
        Criterion("cites_migration_doc", False, lambda r: any(s.migration_doc in c for c in _evidence_ids(r))),
        Criterion("rules_out_firewall", False, lambda r: any("firewall" in x.get("hypothesis", "").lower() for x in report_ruled_out(r))),
        Criterion("confidence_high", False, lambda r: r.get("confidence") == "high"),
        Criterion("has_fix_script", False, lambda r: bool(r.get("proposed_fix_script"))),
    ]


def report_ruled_out(report: dict) -> list[dict]:
    return report.get("ruled_out", []) or []


def grade(report: dict | None, criteria: list[Criterion]) -> dict:
    """Returns {passed, required_failed, criteria: {name: bool}}. A missing
    report (failed run) fails every criterion."""
    results = {c.name: bool(report and _safe(c.check, report)) for c in criteria}
    required_failed = [c.name for c in criteria if c.required and not results[c.name]]
    return {"passed": not required_failed, "required_failed": required_failed, "criteria": results}


def _safe(check: Callable[[dict], bool], report: dict) -> bool:
    try:
        return check(report)
    except Exception:  # noqa: BLE001 - a malformed report is a failed criterion, not a crash
        return False
