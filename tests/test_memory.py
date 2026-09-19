"""Unit tests for Stage 2 persistent memory and deduplication."""
from stage2.models import Query, Escalation
from stage2.memory import CrewMemory
from stage1.models import EvidenceRef


def test_query_fingerprint_deduplication():
    memory = CrewMemory()
    q1 = Query(
        cut=1,
        domain="AE",
        usubjid="042-S01-001",
        seq=1,
        issue_code="AE_BEFORE_FIRST_DOSE",
        text="Verify start date.",
    )
    assert not memory.is_query_duplicate(q1)

    memory.register_query(q1)
    assert memory.is_query_duplicate(q1)

    # Identical record/issue in later cut
    q2 = Query(
        cut=2,
        domain="AE",
        usubjid="042-S01-001",
        seq=1,
        issue_code="AE_BEFORE_FIRST_DOSE",
        text="Verify start date.",
    )
    assert memory.is_query_duplicate(q2)


def test_escalation_rejection_memory():
    memory = CrewMemory()
    esc = Escalation(
        cut=1,
        code="HYS_LAW_CANDIDATE",
        usubjid="042-S07-001",
        site="S07",
        severity="CRITICAL",
        summary="Potential Hy's law",
        rationale="ALT > 3x ULN and BILI > 2x ULN",
        evidence=[EvidenceRef(domain="LB", usubjid="042-S07-001", seq=1)],
    )
    esc.compute_fingerprint()

    assert not memory.is_escalation_duplicate(esc)
    memory.mark_escalation_rejected(esc, reason="Baseline transaminases already elevated")

    # In next cycle, identical finding should not re-escalate
    assert memory.is_escalation_duplicate(esc)
    assert memory.is_escalation_rejected_previously(esc.fingerprint)
