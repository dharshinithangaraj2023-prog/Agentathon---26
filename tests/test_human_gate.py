"""Unit tests for Stage 2 Human Gate (APPROVED, REJECTED, CLARIFY)."""
import os
import pytest
from stage1.atlas import Atlas
from stage2.models import Escalation
from stage2.human_gate import HumanGateNode
from stage2.memory import CrewMemory
from stage1.models import EvidenceRef


@pytest.fixture
def data_dir():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "hackathon-data", "hackathon-data")


def test_human_gate_responses(data_dir):
    atlas = Atlas(data_dir=data_dir)
    atlas.build(cut=1, protocol_version=1)
    memory = CrewMemory()
    gate = HumanGateNode(data_dir=data_dir, query_service=atlas.query_service, memory=memory, trace=atlas.trace)

    # 1. Test APPROVED subject (042-S02-001)
    esc_app = Escalation(
        cut=1,
        code="HYS_LAW_CANDIDATE",
        usubjid="042-S02-001",
        site="S02",
        severity="CRITICAL",
        summary="Hy's law",
        rationale="ALT/BILI elevated",
        evidence=[EvidenceRef(domain="LB", usubjid="042-S02-001", seq=1)],
    )
    processed = gate.process_escalations([esc_app], cut=1, protocol_version=1)
    assert processed[0].status == "APPROVED"
    assert processed[0].action_taken == "REPORT_TO_SAFETY_AND_HOLD_DOSING"

    # 2. Test REJECTED subject (042-S07-001)
    esc_rej = Escalation(
        cut=1,
        code="HYS_LAW_CANDIDATE",
        usubjid="042-S07-001",
        site="S07",
        severity="CRITICAL",
        summary="Hy's law",
        rationale="ALT/BILI elevated",
        evidence=[EvidenceRef(domain="LB", usubjid="042-S07-001", seq=1)],
    )
    processed_rej = gate.process_escalations([esc_rej], cut=1, protocol_version=1)
    assert processed_rej[0].status == "REJECTED"
    assert "Baseline transaminases" in processed_rej[0].monitor_response

    # 3. Test CLARIFY subject (042-S01-001)
    esc_clar = Escalation(
        cut=1,
        code="HYS_LAW_CANDIDATE",
        usubjid="042-S01-001",
        site="S01",
        severity="CRITICAL",
        summary="Hy's law",
        rationale="ALT/BILI elevated",
        evidence=[EvidenceRef(domain="LB", usubjid="042-S01-001", seq=1)],
    )
    processed_clar = gate.process_escalations([esc_clar], cut=1, protocol_version=1)
    # Clarify was queried from graph and resubmitted -> APPROVED
    assert processed_clar[0].status == "APPROVED"
    assert processed_clar[0].clarification_answer is not None
    assert "Screening ALT" in processed_clar[0].clarification_answer
