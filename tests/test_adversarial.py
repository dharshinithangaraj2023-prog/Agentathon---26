"""Unit tests for adversarial pattern detection."""
import os
import pytest
from stage1.atlas import Atlas
from stage1.trace import DecisionTrace
from stage1.graph import StudyGraph
from stage1.models import Subject, LabResult, VitalSign
from stage3.adversarial import AdversarialEngine


@pytest.fixture
def data_dir():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "hackathon-data", "hackathon-data")


def test_site_regularity_vital_anomaly():
    trace = DecisionTrace()
    adv = AdversarialEngine(trace=trace)
    graph = StudyGraph()

    # Create synthetic site with identical vitals across 5 subjects
    for i in range(1, 6):
        subj_id = f"042-S99-{i:03d}"
        subj = Subject(usubjid=subj_id, siteid="S99")
        graph.add_subject(subj)
        for seq in range(1, 4):
            vs = VitalSign(
                usubjid=subj_id,
                seq=seq,
                test_code="SYSBP",
                value_raw="120",
                value_num=120.0,
                cut_available=1,
            )
            graph.add_vital_sign(vs)

    alerts = adv.detect_site_regularity(graph, cut=1, protocol_version=1)
    assert len(alerts) > 0
    assert any(a.alert_type == "SITE_REGULARITY_ANOMALY" and a.site_id == "S99" for a in alerts)


def test_lab_unit_shift_detection():
    trace = DecisionTrace()
    adv = AdversarialEngine(trace=trace)
    graph = StudyGraph()

    # Create site reporting Glucose in mmol/L (~6.4 instead of ~118 mg/dL)
    for i in range(1, 5):
        subj_id = f"042-S98-{i:03d}"
        subj = Subject(usubjid=subj_id, siteid="S98")
        graph.add_subject(subj)
        for seq in range(1, 3):
            lb = LabResult(
                usubjid=subj_id,
                seq=seq,
                test_code="GLUC",
                value_raw="6.4",
                value_num=6.4,
                cut_available=1,
            )
            graph.add_lab_result(lb)

    alerts = adv.detect_lab_unit_shifts(graph, cut=1, protocol_version=1)
    assert len(alerts) > 0
    assert any(a.alert_type == "DATA_INTEGRITY_LAB_UNIT_SHIFT" and a.site_id == "S98" for a in alerts)
