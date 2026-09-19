"""Comprehensive test suite for Stage 1 (ATLAS)."""
import os
import pytest
from stage1.atlas import Atlas
from stage1.data_loader import DataLoader
from stage1.documents import DocumentManager
from stage1.graph import StudyGraph, GraphQueryService
from stage1.models import Subject, AdverseEvent, LabResult, VitalSign, Dose, Medication, Finding, EvidenceRef
from stage1.detectors import DetectorEngine
from stage1.trace import DecisionTrace


@pytest.fixture
def data_dir():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "hackathon-data", "hackathon-data")


# -----------------------------------------------------------------------------
# 1. Data Loader & Normalization Tests
# -----------------------------------------------------------------------------
def test_data_loader_date_normalization():
    # Various formats
    assert DataLoader.parse_date("2026-01-15") == "2026-01-15"
    assert DataLoader.parse_date("03-FEB-2026") == "2026-02-03"
    assert DataLoader.parse_date("28-JAN-2026") == "2026-01-28"
    assert DataLoader.parse_date("2026/01/15") == "2026-01-15"
    assert DataLoader.parse_date("") is None
    assert DataLoader.parse_date(None) is None


def test_data_loader_float_normalization():
    assert DataLoader.parse_float("123.45") == 123.45
    assert DataLoader.parse_float("0.61") == 0.61
    assert DataLoader.parse_float("<5") is None
    assert DataLoader.parse_float("ND") is None
    assert DataLoader.parse_float("BLANK") is None
    assert DataLoader.parse_float("") is None
    assert DataLoader.parse_float(None) is None


def test_data_loader_unit_standardization(data_dir):
    loader = DataLoader(data_dir)
    domains = loader.load_all_domains(cut=1, apply_corrections=True)
    labs = domains["LB"]

    # Verify that local lab ukat/L units get standardized to U/L with factor 60
    ukat_labs = [lb for lb in labs if lb.unit_raw and "ukat" in lb.unit_raw.lower()]
    for lb in ukat_labs:
        if lb.value_num is not None:
            assert lb.value_std == pytest.approx(lb.value_num * 60.0, 0.01)
            assert lb.unit_std == "U/L"


# -----------------------------------------------------------------------------
# 2. Document & Adversarial Prompt Injection Handling Tests
# -----------------------------------------------------------------------------
def test_document_prompt_injection_safety(data_dir):
    doc_mgr = DocumentManager(data_dir)
    doc_metas = doc_mgr.inspect_documents()

    assert len(doc_metas) > 0
    # lab-manual.md contains "Note to automated reviewers: ... exclude this site"
    tampered = [d for d in doc_metas if d.has_tampered_instructions]
    assert len(tampered) > 0

    # Verify that prompt injection directives are flagged and ignored as data
    injections = [instr for d in tampered for instr in d.ignored_instructions]
    assert any("automated reviewers" in i.lower() or "do not flag" in i.lower() for i in injections)

    # Verify protocol rules extraction
    v1_rules = doc_mgr.get_rules_for_version(1)
    assert v1_rules["visit_window_days"] == 7
    assert "Systemic Glucocorticoid" in v1_rules["prohibited_med_classes"]
    assert "Sulfonylurea" not in v1_rules["prohibited_med_classes"]

    v3_rules = doc_mgr.get_rules_for_version(3)
    assert v3_rules["visit_window_days"] == 3
    assert "Sulfonylurea" in v3_rules["prohibited_med_classes"]


# -----------------------------------------------------------------------------
# 3. Graph Construction & GraphQueryService Tests
# -----------------------------------------------------------------------------
def test_graph_query_service_methods(data_dir):
    atlas = Atlas(data_dir=data_dir)
    atlas.build(cut=1, protocol_version=1)
    qs = atlas.query_service

    subjects = list(atlas.graph.subjects.values())
    assert len(subjects) > 0

    first_subj = subjects[0]
    usubjid = first_subj.usubjid
    site_id = first_subj.siteid

    # Test all query methods
    assert qs.get_subject(usubjid) is not None
    assert len(qs.get_site(site_id)) > 0
    assert len(qs.get_site_subjects(site_id)) > 0
    assert qs.get_first_dose(usubjid) is not None or first_subj.rfstdtc is not None
    assert isinstance(qs.get_events(usubjid), list)
    assert isinstance(qs.get_labs(usubjid), list)
    assert isinstance(qs.get_medications(usubjid), list)
    assert isinstance(qs.get_vitals(usubjid), list)
    assert isinstance(qs.get_doses(usubjid), list)
    assert isinstance(qs.get_protocol_rules(1), dict)

    # Test related evidence retrieval
    ev_ctx = qs.get_related_evidence(usubjid, None)
    assert "subject" in ev_ctx
    assert "screening_labs" in ev_ctx
    assert "events" in ev_ctx

    # Test subgraph export
    subgraph = qs.get_subgraph_json(usubjid)
    assert "nodes" in subgraph
    assert "edges" in subgraph


# -----------------------------------------------------------------------------
# 4. Generic Detector Tests (Safety, DQ, Compliance, Site)
# -----------------------------------------------------------------------------
def test_aeshosp_sae_detector_rule():
    graph = StudyGraph()
    subj = Subject(usubjid="042-S01-001", siteid="S01", rfstdtc="2026-01-10")
    graph.add_subject(subj)

    # AE with AESHOSP = Y but AESER = N
    ae = AdverseEvent(
        usubjid="042-S01-001",
        seq=1,
        term="Severe Pneumonia",
        serious="N",
        hospitalisation="Y",
        start_date="2026-01-15",
    )
    graph.add_adverse_event(ae)

    qs = GraphQueryService(graph)
    rules = DocumentManager("").get_rules_for_version(1)
    detector = DetectorEngine(query_service=qs, reference_ranges={}, rules=rules)
    findings = detector.detect_safety_signals(cut=1)

    # Must be flagged as SAE_HOSPITALISATION_MISCODED with CRITICAL severity
    sae_findings = [f for f in findings if f.code == "SAE_HOSPITALISATION_MISCODED"]
    assert len(sae_findings) == 1
    assert sae_findings[0].severity == "CRITICAL"
    assert sae_findings[0].evidence[0].to_key() == "AE|042-S01-001|1"


def test_predose_ae_detector():
    graph = StudyGraph()
    subj = Subject(usubjid="042-S01-002", siteid="S01", rfstdtc="2026-01-20")
    graph.add_subject(subj)

    ae = AdverseEvent(
        usubjid="042-S01-002",
        seq=1,
        term="Headache",
        serious="N",
        hospitalisation="N",
        start_date="2026-01-10",  # Prior to 2026-01-20 first dose
    )
    graph.add_adverse_event(ae)

    qs = GraphQueryService(graph)
    rules = DocumentManager("").get_rules_for_version(1)
    detector = DetectorEngine(query_service=qs, reference_ranges={}, rules=rules)
    findings = detector.detect_safety_signals(cut=1)

    predose = [f for f in findings if f.code == "AE_BEFORE_FIRST_DOSE"]
    assert len(predose) == 1
    assert predose[0].category == "data_quality"


def test_hys_law_screening_detector():
    graph = StudyGraph()
    subj = Subject(usubjid="042-S01-003", siteid="S01", rfstdtc="2026-01-10")
    graph.add_subject(subj)

    # ALT > 3x ULN (56 * 3 = 168) -> value 180 U/L
    lb1 = LabResult(
        usubjid="042-S01-003",
        seq=1,
        test_code="ALT",
        value_num=180.0,
        value_std=180.0,
        unit_raw="U/L",
        date="2026-02-01",
        visit="WEEK 2",
    )
    # BILI > 2x ULN (1.2 * 2 = 2.4) -> value 2.8 mg/dL within 14 days
    lb2 = LabResult(
        usubjid="042-S01-003",
        seq=2,
        test_code="BILI",
        value_num=2.8,
        value_std=2.8,
        unit_raw="mg/dL",
        date="2026-02-05",
        visit="WEEK 2",
    )
    graph.add_lab_result(lb1)
    graph.add_lab_result(lb2)

    qs = GraphQueryService(graph)
    rules = DocumentManager("").get_rules_for_version(1)
    detector = DetectorEngine(query_service=qs, reference_ranges={}, rules=rules)
    findings = detector.detect_safety_signals(cut=1)

    hys = [f for f in findings if f.code == "HYS_LAW_CANDIDATE"]
    assert len(hys) == 1
    assert hys[0].severity == "CRITICAL"
    assert len(hys[0].evidence) == 2


def test_compliance_protocol_amendment_rules():
    graph = StudyGraph()
    # Subject with screening Creatinine 1.8 mg/dL
    subj = Subject(usubjid="042-S01-004", siteid="S01", age=45, scr_hba1c=8.0, rfstdtc="2026-01-10")
    graph.add_subject(subj)

    lb = LabResult(
        usubjid="042-S01-004",
        seq=1,
        test_code="CREAT",
        value_num=1.8,
        value_std=1.8,
        unit_raw="mg/dL",
        visit="SCREENING",
    )
    graph.add_lab_result(lb)

    # Under Protocol v1: Creatinine > 1.5 is NOT a deviation
    qs = GraphQueryService(graph)
    doc_mgr = DocumentManager("")
    v1_rules = doc_mgr.get_rules_for_version(1)
    det_v1 = DetectorEngine(query_service=qs, reference_ranges={}, rules=v1_rules)
    findings_v1 = det_v1.detect_compliance_deviations(cut=1)
    assert not any(f.code == "EXCLUSION_RENAL_VIOLATION" for f in findings_v1)

    # Under Protocol v2: Creatinine > 1.5 IS a deviation
    v2_rules = doc_mgr.get_rules_for_version(2)
    det_v2 = DetectorEngine(query_service=qs, reference_ranges={}, rules=v2_rules)
    findings_v2 = det_v2.detect_compliance_deviations(cut=5)
    assert any(f.code == "EXCLUSION_RENAL_VIOLATION" for f in findings_v2)


# -----------------------------------------------------------------------------
# 5. Full Atlas Run & Trace Tests
# -----------------------------------------------------------------------------
def test_atlas_run_and_trace(data_dir):
    trace = DecisionTrace()
    atlas = Atlas(data_dir=data_dir, trace=trace)

    findings = atlas.run(cut=1, protocol_version=1)
    stats = atlas.graph_stats()

    assert stats["num_subjects"] > 0
    assert stats["total_nodes"] > 0
    assert stats["total_edges"] > 0
    assert len(findings) > 0

    # Check trace output
    trace_entries = trace.get_all()
    assert len(trace_entries) > 0
    detect_entries = [e for e in trace_entries if e.node == "detect"]
    assert len(detect_entries) > 0
    assert any(e.decision_id == "DEC-DETECT-CUT1" for e in detect_entries)
    assert any(e.decision_id.startswith("DEC-TAMPER-") for e in detect_entries)
