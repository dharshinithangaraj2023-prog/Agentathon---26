"""Comprehensive unit test suite for Stage 2 (MONITOR) ReviewCrew."""
import os
import pytest
from stage1.atlas import Atlas
from stage1.graph import StudyGraph
from stage1.models import Subject, AdverseEvent, LabResult, Finding, EvidenceRef
from stage2.crew import ReviewCrew
from stage2.memory import CrewMemory
from stage2.human_gate import HumanGateNode
from stage2.models import Escalation


@pytest.fixture
def data_dir():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "hackathon-data", "hackathon-data")


# -----------------------------------------------------------------------------
# 1. Six-Node Sequence & Cycle Execution
# -----------------------------------------------------------------------------
def test_six_node_strict_sequence_and_trace(data_dir):
    atlas = Atlas(data_dir=data_dir)
    crew = ReviewCrew(atlas=atlas)

    result = crew.run_cycle(cut=1, protocol_version=1)

    assert result.cut == 1
    assert result.protocol_version == 1
    assert result.findings_count > 0
    assert result.report is not None

    # Verify execution order in state summary
    execution_order = result.summary.get("execution_order")
    expected_order = ["detect", "medical_review", "data_manager", "compliance", "human_gate", "execute"]
    assert execution_order == expected_order

    # Verify all 6 nodes wrote immutable trace entries
    trace_entries = crew.trace.get_by_cut(1)
    nodes_in_trace = {e.node for e in trace_entries}
    for expected_node in expected_order:
        assert expected_node in nodes_in_trace


# -----------------------------------------------------------------------------
# 2. Cycle 1 -> Cycle 1 Repeat: 0 New Queries, 0 New Escalations
# -----------------------------------------------------------------------------
def test_cycle_repeat_zero_new_queries_zero_new_escalations(data_dir):
    memory = CrewMemory()
    atlas = Atlas(data_dir=data_dir)
    crew = ReviewCrew(atlas=atlas, memory=memory)

    # First cycle execution on Cut 1
    res1 = crew.run_cycle(cut=1, protocol_version=1)
    assert len(res1.queries) > 0

    # Second cycle execution on identical Cut 1
    res2 = crew.run_cycle(cut=1, protocol_version=1)
    assert len(res2.queries) == 0  # 0 new duplicate queries
    assert len(res2.escalations) == 0  # 0 new duplicate escalations


# -----------------------------------------------------------------------------
# 3. All Three Human Gate Replies (APPROVED, REJECTED, CLARIFY)
# -----------------------------------------------------------------------------
def test_human_gate_all_three_replies(data_dir):
    atlas = Atlas(data_dir=data_dir)
    atlas.build(cut=1, protocol_version=1)
    memory = CrewMemory()
    gate = HumanGateNode(data_dir=data_dir, query_service=atlas.query_service, memory=memory, trace=atlas.trace)

    # 1. APPROVED Case (042-S02-001)
    esc_app = Escalation(
        cut=1,
        code="HYS_LAW_CANDIDATE",
        usubjid="042-S02-001",
        site="S02",
        severity="CRITICAL",
        summary="Hy's law candidate",
        rationale="ALT > 3x ULN and BILI > 2x ULN",
        evidence=[EvidenceRef(domain="LB", usubjid="042-S02-001", seq=1)],
    )
    res_app = gate.process_escalations([esc_app], cut=1, protocol_version=1)
    assert res_app[0].status == "APPROVED"
    assert res_app[0].action_taken == "REPORT_TO_SAFETY_AND_HOLD_DOSING"

    # 2. REJECTED Case (042-S07-001)
    esc_rej = Escalation(
        cut=1,
        code="HYS_LAW_CANDIDATE",
        usubjid="042-S07-001",
        site="S07",
        severity="CRITICAL",
        summary="Hy's law candidate",
        rationale="ALT > 3x ULN and BILI > 2x ULN",
        evidence=[EvidenceRef(domain="LB", usubjid="042-S07-001", seq=1)],
    )
    res_rej = gate.process_escalations([esc_rej], cut=1, protocol_version=1)
    assert res_rej[0].status == "REJECTED"
    assert res_rej[0].action_taken == "DOWNGRADE_TO_MONITORING"
    # Ensure memory prevents future re-escalation
    assert memory.is_escalation_rejected_previously(esc_rej.compute_fingerprint())

    # 3. CLARIFY Case (042-S01-001)
    esc_clar = Escalation(
        cut=1,
        code="HYS_LAW_CANDIDATE",
        usubjid="042-S01-001",
        site="S01",
        severity="CRITICAL",
        summary="Hy's law candidate",
        rationale="ALT > 3x ULN and BILI > 2x ULN",
        evidence=[EvidenceRef(domain="LB", usubjid="042-S01-001", seq=1)],
    )
    res_clar = gate.process_escalations([esc_clar], cut=1, protocol_version=1)
    assert res_clar[0].status == "APPROVED"
    assert res_clar[0].clarification_answer is not None
    assert "Screening ALT" in res_clar[0].clarification_answer


# -----------------------------------------------------------------------------
# 4. AESHOSP=Y with AESER=N Generic Handling
# -----------------------------------------------------------------------------
def test_aeshosp_miscoded_escalation_flow(data_dir):
    atlas = Atlas(data_dir=data_dir)
    crew = ReviewCrew(atlas=atlas)
    # Cut 6 contains the actual miscoded hospitalization AE (042-S02-004)
    result = crew.run_cycle(cut=6, protocol_version=2)

    # Must be drafted and submitted through medical review / human gate as SAE
    sae_escalations = [e for e in result.escalations if e.code == "SAE_HOSPITALISATION_MISCODED"]
    assert len(sae_escalations) >= 1
    assert sae_escalations[0].severity == "CRITICAL"
    assert sae_escalations[0].status == "APPROVED"


# -----------------------------------------------------------------------------
# 5. Event Before Dose Becomes Query (Not Escalation)
# -----------------------------------------------------------------------------
def test_event_before_dose_becomes_query_not_escalation(data_dir):
    atlas = Atlas(data_dir=data_dir)
    crew = ReviewCrew(atlas=atlas)
    result = crew.run_cycle(cut=1, protocol_version=1)

    # Must generate data quality queries for pre-dose AEs
    predose_queries = [q for q in result.queries if q.issue_code == "AE_BEFORE_FIRST_DOSE"]
    assert len(predose_queries) > 0
    assert predose_queries[0].domain == "AE"
    assert "first study dose" in predose_queries[0].text

    # Must NOT generate an escalation for pre-dose AEs
    predose_escalations = [e for e in result.escalations if e.code == "AE_BEFORE_FIRST_DOSE"]
    assert len(predose_escalations) == 0


# -----------------------------------------------------------------------------
# 6. Subject Recurrence Priority Boosting & Site Risk Counters
# -----------------------------------------------------------------------------
def test_subject_recurrence_priority_and_site_risk(data_dir):
    memory = CrewMemory()
    atlas = Atlas(data_dir=data_dir)
    crew = ReviewCrew(atlas=atlas, memory=memory)

    # Record flag for subject in Cut 1
    prior_c1 = memory.record_subject_flag("042-S01-001", cut=1)
    assert prior_c1 == 0

    # In Cut 2, subject has been flagged in 1 prior cycle -> priority level = 2
    prior_c2 = memory.record_subject_flag("042-S01-001", cut=2)
    assert prior_c2 == 1

    # Record site issues and verify site risk level increments
    for i in range(5):
        memory.record_site_issue("S01", f"DEV_{i}")

    assert memory.site_risks["S01"]["total_issues"] >= 5
    assert memory.site_risks["S01"]["risk_level"] in ["MEDIUM", "HIGH"]
