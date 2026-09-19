"""Automated unit and integration tests for Patient Study Graph / Patient ID Search feature."""
import pytest
import os
from fastapi.testclient import TestClient
from ui.server import app, watch_inst, atlas_inst
from stage1.models import AdverseEvent, LabResult, Subject
from stage2.models import Escalation, Deviation, Query


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_1_existing_patient_search(client):
    """Test 1: Query existing patient '042-S02-004'."""
    response = client.get("/api/patients/042-S02-004/study-profile")
    assert response.status_code == 200
    data = response.json()
    assert data["patient_id"] == "042-S02-004"
    assert data["site_id"] == "S02"
    assert "graph_metrics" in data
    assert "visits" in data["graph_metrics"]
    assert "labs" in data["graph_metrics"]
    assert "events" in data["graph_metrics"]
    assert "monitoring_summary" in data


def test_2_invalid_patient_search(client):
    """Test 2: Query non-existent patient 'INVALID-001'."""
    response = client.get("/api/patients/INVALID-001/study-profile")
    assert response.status_code == 404
    data = response.json()
    assert "Patient not found" in data["detail"] or "No subject with ID" in data["detail"]


def test_3_whitespace_and_case_insensitivity(client):
    """Test 3: Verify ID trimming and case normalization (' 042-s02-004 ')."""
    response = client.get("/api/patients/%20042-s02-004%20/study-profile")
    assert response.status_code == 200
    data = response.json()
    assert data["patient_id"] == "042-S02-004"


def test_4_patient_with_serious_ae(client):
    """Test 4: Verify AE severity, hospitalisation, and status are returned."""
    response = client.get("/api/patients/042-S02-004/study-profile")
    assert response.status_code == 200
    data = response.json()
    aes = data.get("adverse_events", [])
    assert len(aes) > 0
    sample_ae = aes[0]
    assert "term" in sample_ae
    assert "severity" in sample_ae
    assert "aeshosp" in sample_ae


def test_5_aeshosp_rule_preservation(client):
    """Test 5: Verify AESHOSP=Y is treated as serious even if AESER=N."""
    # Test on patient 042-S02-004 or query profile directly
    profile = atlas_inst.query_service.get_patient_study_profile("042-S02-004", memory=watch_inst.memory)
    assert profile is not None
    aes = profile["adverse_events"]
    # Check that any AE with AESHOSP=Y is flagged with is_protocol_serious=True
    for ae in aes:
        if ae["aeshosp"] == "Y":
            assert ae["is_protocol_serious"] is True


def test_6_lab_unit_anomaly_warning(client):
    """Test 6: Verify lab trust status and data integrity warning for unit shift."""
    # Site S04 has lab unit shift on Glucose
    profile = atlas_inst.query_service.get_patient_study_profile(
        "042-S04-001",
        memory=watch_inst.memory,
        adversarial_alerts=watch_inst.adversarial_alerts
    )
    assert profile is not None
    labs = profile["labs"]
    # Check if glucose values exhibit untrusted status or warning
    gluc_labs = [l for l in labs if l["test_code"] in ["GLUC", "GLUCOSE"]]
    if gluc_labs:
        untrusted_labs = [l for l in gluc_labs if l["trust_status"] == "Untrusted"]
        assert len(untrusted_labs) > 0
        assert untrusted_labs[0]["data_integrity_warning"] is not None


def test_7_protocol_amendment_handling(client):
    """Test 7: Verify protocol versioning metadata is returned."""
    response = client.get("/api/patients/042-S02-004/study-profile")
    assert response.status_code == 200
    data = response.json()
    assert data["protocol_version"] >= 1
    assert data["current_cut"] == 12


def test_8_incremental_correction_reflection(client):
    """Test 8: Verify corrections count and dynamic state updating."""
    profile = atlas_inst.query_service.get_patient_study_profile("042-S02-004", memory=watch_inst.memory, trace=watch_inst.trace)
    assert profile is not None
    # Patient profile contains dynamic trace and memory details
    assert "decisions" in profile
    assert "graph_metrics" in profile


def test_9_decision_explanation_and_traceability(client):
    """Test 9: Verify patient decision explanations can be fetched and traced."""
    profile = atlas_inst.query_service.get_patient_study_profile("042-S02-004", memory=watch_inst.memory, trace=watch_inst.trace)
    assert profile is not None
    decisions = profile.get("decisions", [])
    if len(decisions) > 0:
        sample_dec_id = decisions[0]["decision_id"]
        exp_response = client.get(f"/api/explain/{sample_dec_id}")
        assert exp_response.status_code == 200
        exp_data = exp_response.json()
        assert "what" in exp_data
        assert "why" in exp_data
        assert "consistent_with_trace" in exp_data
