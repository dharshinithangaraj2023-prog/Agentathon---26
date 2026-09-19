"""Test suite verifying all FastAPI UI endpoints and demo payloads."""
import pytest
from fastapi.testclient import TestClient
from ui.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_ui_index_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Study Sentinel" in res.text


def test_ui_status_endpoint(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "OPERATIONAL"
    assert data["current_cut"] == 12
    assert data["protocol_version"] == 3
    assert data["total_trace_entries"] > 0
    assert "budget" in data


def test_ui_cuts_summary_endpoint(client):
    res = client.get("/api/cuts-summary")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 12
    assert data[0]["cut"] == 1
    assert data[11]["cut"] == 12


def test_ui_cut_details_endpoint(client):
    res = client.get("/api/cut/6/details")
    assert res.status_code == 200
    data = res.json()
    assert data["cut"] == 6
    assert "escalations" in data
    assert "queries" in data
    assert "trace_entries" in data


def test_ui_cycle_report_endpoint(client):
    res = client.get("/api/cycle-report/12")
    assert res.status_code == 200
    data = res.json()
    assert len(data["nodes"]) == 6
    node_names = [n["node"] for n in data["nodes"]]
    assert node_names == ["detect", "medical_review", "data_manager", "compliance", "human_gate", "execute"]


def test_ui_clarify_demo_endpoint(client):
    res = client.get("/api/human-gate/clarify-demo")
    assert res.status_code == 200
    data = res.json()
    assert "screening_labs" in data["graph_lookup"]
    assert data["resubmission_status"] == "APPROVED"


def test_ui_adversarial_summary_endpoint(client):
    res = client.get("/api/adversarial-summary")
    assert res.status_code == 200
    data = res.json()
    assert len(data["categories"]) == 4
    cat_ids = [c["id"] for c in data["categories"]]
    assert "regular_site" in cat_ids
    assert "unit_shift" in cat_ids
    assert "document_tampering" in cat_ids
    assert "protocol_amendment" in cat_ids


def test_ui_graph_and_subjects_endpoints(client):
    res_subjs = client.get("/api/subjects")
    assert res_subjs.status_code == 200
    subjs = res_subjs.json()
    assert len(subjs) > 0

    first_usubjid = subjs[0]["usubjid"]
    res_graph = client.get(f"/api/graph/{first_usubjid}")
    assert res_graph.status_code == 200
    g_data = res_graph.json()
    assert "graph" in g_data
    assert "events" in g_data


def test_ui_explain_and_report_endpoints(client):
    res_trace = client.get("/api/trace")
    assert res_trace.status_code == 200
    traces = res_trace.json()
    assert len(traces) > 0

    sample_dec_id = traces[-1]["decision_id"]
    res_exp = client.get(f"/api/explain/{sample_dec_id}")
    assert res_exp.status_code == 200
    exp = res_exp.json()
    assert exp["consistent_with_trace"] is True

    res_rep = client.get("/api/report")
    assert res_rep.status_code == 200
    assert "report_markdown" in res_rep.json()
