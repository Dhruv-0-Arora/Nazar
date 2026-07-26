import json

import pytest

from brain.agent.protocol import ProtocolError, parse_turn
from brain.report import ReportError, parse_report, render_markdown
from conftest import ENV_CHUNK, scripted_diagnosis


def test_parse_turn_accepts_scripted_turns():
    for raw in scripted_diagnosis()[:3]:
        turn = parse_turn(raw)
        assert isinstance(turn.conclude, bool)


def test_parse_turn_strips_code_fences():
    fenced = "```json\n" + scripted_diagnosis()[0] + "\n```"
    assert parse_turn(fenced).actions


def test_parse_turn_rejects_garbage():
    with pytest.raises(ProtocolError, match="not valid JSON"):
        parse_turn("I think the problem is DNS")
    with pytest.raises(ProtocolError, match="schema violation"):
        parse_turn('{"actions": [{"op": "teleport"}]}')


def test_report_strips_dangling_citations():
    raw = scripted_diagnosis()[3]
    report, warnings = parse_report(raw, known_chunk_ids={ENV_CHUNK, "laptop-a:app_logs/backend.log:L1-L4"})
    assert len(report.evidence) == 2
    assert any("bogus" in w for w in warnings)


def test_report_schema_violation_raises():
    with pytest.raises(ReportError):
        parse_report(json.dumps({"root_cause": "x", "confidence": "certain"}), set())


def test_render_markdown_contains_the_essentials():
    report, _ = parse_report(scripted_diagnosis()[3], known_chunk_ids={ENV_CHUNK})
    md = render_markdown(report, run_id="run-x", elapsed_s=19.4, bundle_ids=["b1"], query_trail=["turn 1: searched"])
    assert "# Diagnosis - run-x" in md
    assert "never executed by the Brain" in md
    assert ENV_CHUNK in md
