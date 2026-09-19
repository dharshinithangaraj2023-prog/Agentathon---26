"""Unit tests for trace-backed explainability."""
from stage1.trace import DecisionTrace
from stage3.explanation import ExplanationEngine


def test_explain_decision_id_lookup():
    trace = DecisionTrace()
    entry = trace.record(
        cut=3,
        protocol_version=1,
        node="medical_review",
        decision_id="DEC-MED-DRAFT-ESC-1234",
        action="DRAFT_ESCALATION",
        finding_id="F-SAE-042-S02-001-1",
        subject="042-S02-001",
        site="S02",
        reason="SAE hospitalisation miscoded as non-serious.",
        evidence_lines=["AE record #1: Hospitalization flag Y with AESER N"],
        evidence_refs=[{"domain": "AE", "usubjid": "042-S02-001", "seq": 1}],
        alternatives=["Maintain as non-serious"],
    )

    engine = ExplanationEngine(trace=trace)
    explanation = engine.explain("DEC-MED-DRAFT-ESC-1234")

    assert explanation.decision_id == "DEC-MED-DRAFT-ESC-1234"
    assert explanation.what == "DRAFT_ESCALATION"
    assert explanation.why == "SAE hospitalisation miscoded as non-serious."
    assert len(explanation.evidence_lines) > 0
    assert explanation.consistent_with_trace is True
    assert explanation.node == "medical_review"
    assert explanation.cut == 3


def test_explain_unknown_decision():
    trace = DecisionTrace()
    engine = ExplanationEngine(trace=trace)
    explanation = engine.explain("DEC-NONEXISTENT")

    assert explanation.consistent_with_trace is False
    assert explanation.node == "unknown"
