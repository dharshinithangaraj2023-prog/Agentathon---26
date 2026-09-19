"""Comprehensive unit test suite for Stage 3 (WATCH)."""
import os
import pytest
from stage1.atlas import Atlas
from stage1.models import Subject, LabResult, Finding, EvidenceRef
from stage2.crew import ReviewCrew
from stage2.models import Escalation
from stage3.watch import StudyWatch, PendingEscalationStore
from stage3.budget import BudgetManager


@pytest.fixture
def data_dir():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "hackathon-data", "hackathon-data")


# -----------------------------------------------------------------------------
# 1. Full 12-Cut Run Execution & Report Persistence
# -----------------------------------------------------------------------------
def test_watch_12_cuts_execution(data_dir):
    atlas = Atlas(data_dir=data_dir)
    crew = ReviewCrew(atlas=atlas)
    watch = StudyWatch(data_dir=data_dir, crew=crew, max_budget_seconds=300.0)

    summary = watch.run_period(cuts=range(1, 13))

    assert len(summary["cuts_evaluated"]) == 12
    assert summary["total_trace_entries"] > 0
    assert summary["applied_corrections"] > 0
    assert os.path.exists("outputs/surveillance_report.md")
    assert os.path.exists("outputs/decision_trace.json")

    # Verify that the non-technical report contains all essential sections
    report_md = watch.latest_report.markdown_content
    assert "Executive Summary" in report_md
    assert "Safety Signals" in report_md
    assert "Data Quality" in report_md
    assert "Compliance" in report_md
    assert "Adversarial" in report_md
    assert "Human Decisions" in report_md
    assert "Budget" in report_md


# -----------------------------------------------------------------------------
# 2. Incremental Graph Corrections Handling
# -----------------------------------------------------------------------------
def test_incremental_corrections_application(data_dir):
    atlas = Atlas(data_dir=data_dir)
    crew = ReviewCrew(atlas=atlas)
    watch = StudyWatch(data_dir=data_dir, crew=crew)

    # Cut 5 contains retroactive lab re-issues from corrections.csv
    watch.run_period(cuts=range(1, 6))

    assert watch.incremental_engine.applied_corrections_count > 0
    # Trace must contain incremental correction entries
    corrs = [e for e in crew.trace.get_all() if e.action == "APPLY_INCREMENTAL_CORRECTION"]
    assert len(corrs) > 0
    assert "applied retroactive correction" in corrs[0].reason.lower()


# -----------------------------------------------------------------------------
# 3. Delayed Human & 4-Cut Unanswered Escalation Rule
# -----------------------------------------------------------------------------
def test_delayed_human_and_four_cut_unanswered_rule(data_dir):
    atlas = Atlas(data_dir=data_dir)
    crew = ReviewCrew(atlas=atlas)
    watch = StudyWatch(data_dir=data_dir, crew=crew)

    # Register an unanswered escalation at Cut 1
    mock_esc = Escalation(
        cut=1,
        code="UNRESOLVED_SAFETY_SIGNAL",
        usubjid="042-S09-999",
        site="S09",
        severity="CRITICAL",
        summary="Test pending",
        rationale="Testing 4-cut rule",
        status="PENDING",
        created_at_cut=1,
        evidence=[EvidenceRef(domain="AE", usubjid="042-S09-999", seq=1)],
    )
    watch.pending_store.add_pending(mock_esc)

    # Advance to Cut 5 (4 cycles later)
    watch.pending_store.age_pending_escalations(cut=5, protocol_version=2)

    # Must remain PENDING (never implicitly approved)
    assert mock_esc.status == "PENDING"
    assert mock_esc.cycles_pending == 4

    # Must log standing limits warning explicitly
    trace_entries = crew.trace.get_by_cut(5)
    standing_logs = [e for e in trace_entries if e.action == "UNANSWERED_ESCALATION_STANDING_LIMITS"]
    assert len(standing_logs) == 1
    assert "standing limits" in standing_logs[0].reason.lower()


# -----------------------------------------------------------------------------
# 4. Protocol Amendments (v1 -> v2 -> v3) Invalidation & Recomputation
# -----------------------------------------------------------------------------
def test_protocol_amendment_handling(data_dir):
    atlas = Atlas(data_dir=data_dir)
    crew = ReviewCrew(atlas=atlas)
    watch = StudyWatch(data_dir=data_dir, crew=crew)

    watch.run_period(cuts=range(1, 10))

    # Cut 1-4: Protocol v1; Cut 5-8: Protocol v2; Cut 9-12: Protocol v3
    assert watch.atlas.data_loader.get_protocol_version_for_cut(4) == 1
    assert watch.atlas.data_loader.get_protocol_version_for_cut(5) == 2
    assert watch.atlas.data_loader.get_protocol_version_for_cut(9) == 3


# -----------------------------------------------------------------------------
# 5. Dynamic Onboarding of New Sites and New Domains
# -----------------------------------------------------------------------------
def test_dynamic_onboarding_new_site_and_domain(data_dir):
    atlas = Atlas(data_dir=data_dir)
    atlas.build(cut=1, protocol_version=1)

    # Dynamically inject a brand new site "S999" and subject "042-S999-001"
    new_subj = Subject(usubjid="042-S999-001", siteid="S999", age=50, scr_hba1c=8.2, rfstdtc="2026-01-01")
    atlas.graph.add_subject(new_subj)

    # Graph must automatically discover new site without code modifications
    assert "S999" in atlas.graph.sites
    assert "042-S999-001" in atlas.graph.subjects
    assert len(atlas.query_service.get_site("S999")) == 1


# -----------------------------------------------------------------------------
# 6. Global Budget Tier Degradation (FULL -> REDUCED -> MINIMAL)
# -----------------------------------------------------------------------------
def test_budget_manager_tier_degradation():
    bm = BudgetManager(max_seconds=10.0, max_tokens=1000)
    bm.start()

    # Initial state: FULL tier
    assert bm.get_tier() == "FULL"
    assert bm.can_run_expensive_op() is True

    # Consume 85% tokens -> REDUCED tier
    bm.record_operation("heavy_narrative", tokens=850, is_expensive=True)
    assert bm.get_tier() == "REDUCED"
    assert bm.can_run_expensive_op() is False

    # Consume 96% tokens -> MINIMAL tier
    bm.record_operation("extra_tokens", tokens=110)
    assert bm.get_tier() == "MINIMAL"
    assert bm.can_run_expensive_op() is False
