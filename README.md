# Study Sentinel — Integrated Clinical Study Surveillance Platform

An end-to-end explainable, graph-powered clinical surveillance system integrating **ATLAS** (Stage 1), **MONITOR** (Stage 2), and **WATCH** (Stage 3) for Phase III clinical trial data monitoring, multi-agent review, 12-cut unattended surveillance, adversarial detection, and deterministic trace-backed explainability.

---

## System Architecture

The platform operates as a unified, tightly-coupled multi-stage engine:

```
ATLAS (Stage 1: Ingestion & Knowledge Graph)
   │
   ▼
MONITOR (Stage 2: 6-Node Review Crew & Human Gate)
   │
   ▼
WATCH (Stage 3: 12-Cut Incremental Surveillance, Adversarial Quarantines & Trace-Backed Explainability)
```

### Stage 1 — ATLAS (`stage1/`)
- **Schema-Driven Ingestion**: Dynamically loads 9 clinical domains (`DM`, `AE`, `LB`, `VS`, `EX`, `CM`, `DS`, `MH`, `EG`) without hardcoded site/subject identifiers.
- **Unit Standardization**: Normalizes test units (e.g. `1 µkat/L = 60 U/L`) using dynamic `reference_ranges.csv`.
- **Relational Knowledge Graph (`StudyGraph`)**: In-memory NetworkX relational representation linking `Study -> Site -> Subject -> {Visits, Doses, Labs, Adverse Events, Medications}`.
- **Document Manager**: Treats protocol markdown documents as passive data, calculates SHA-256 hashes, detects tampering, and ignores adversarial prompt injections (`AUTOMATED_INSTRUCTION_IGNORED`).
- **Generic Detectors**:
  - **Safety**: Miscoded SAEs (`AESHOSP=Y` with `AESER=N` per Protocol §6), Potential Hy's Law hepatotoxicity (`ALT/AST > 3x ULN + BILI > 2x ULN within 14d`), Pre-dose AEs.
  - **Data Quality**: Missing dose exposure records, non-standard lab entries.
  - **Compliance**: Dynamic protocol rules per version (Age limits, HbA1c screening range, screening Creatinine > 1.5 mg/dL added in v2/v3, visit windows +/-7d vs +/-3d, prohibited meds including Sulfonylureas in v3).

### Stage 2 — MONITOR (`stage2/`)
- **6-Node Sequential Review Crew**:
  1. `detect`: Uses Stage 1 ATLAS finding detectors.
  2. `medical_review`: Separates critical escalation drafts from monitoring-only cases (e.g., elevated screening baseline transaminases).
  3. `data_manager`: Generates exact, single-action queries citing `(domain, usubjid, seq)` and interfaces with site replies.
  4. `compliance`: Evaluates deviations under the active protocol version in force.
  5. `human_gate`: Interfaces with the Medical Monitor gate:
     - `APPROVED`: Executes action (e.g. hold dosing / notify safety).
     - `REJECTED`: Downgrades to monitoring, records rejection reason, suppresses repeat escalations.
     - `CLARIFY`: Traverses the knowledge graph to answer medical queries (screening labs & concomitant drugs), resubmitting for immediate approval.
  6. `execute`: Commits cycle results and updates persistent state.
- **Persistent Crew Memory**: MD5/SHA-256 query and escalation fingerprinting guarantees **0 duplicate queries / 0 duplicate escalations** across repeat runs.

### Stage 3 — WATCH (`stage3/`)
- **12-Cut Unattended Surveillance Loop**: Executes weekly cuts (1 through 12).
- **Incremental Graph Updates**: Applies delta records and `corrections.csv` retroactive changes incrementally without rebuilding from scratch.
- **Adversarial Interception Engine**:
  - **Site Regularity Anomaly**: Catches implausibly zero vital sign variance or duplicated narratives across site patients; quarantines data and flags for audit.
  - **Lab Unit Corruption**: Detects site-wide distribution shifts (e.g. Glucose ratio ~18x indicating mg/dL to mmol/L conversion); quarantines values and raises data quality queries, preventing false safety alarms.
  - **Document Tampering**: Detects hash drifts and prompt injections.
- **Delayed Human Responses**: Tracks pending escalation aging across cycles; enforces the 4-cut unanswered rule under standing limits without auto-approval or silent closure.
- **Global Budget Manager**: Tiered degradation (`FULL` -> `REDUCED` at 80% -> `MINIMAL` at 95%) ensuring deterministic safety monitoring completes with zero crashes.
- **Trace-Backed Explainability**: `explain(decision_id)` resolves strictly against the immutable append-only decision trace (`consistent_with_trace = True`).
- **Surveillance Reporting**: Generates comprehensive non-technical executive reports in `outputs/surveillance_report.md`.

---

## Directory Structure

```
.
├── stage1/                    # Stage 1: ATLAS
│   ├── atlas.py
│   ├── data_loader.py
│   ├── detectors.py
│   ├── documents.py
│   ├── graph.py
│   ├── models.py
│   └── trace.py
├── stage2/                    # Stage 2: MONITOR
│   ├── compliance.py
│   ├── crew.py
│   ├── data_manager.py
│   ├── human_gate.py
│   ├── medical_review.py
│   ├── memory.py
│   └── models.py
├── stage3/                    # Stage 3: WATCH
│   ├── adversarial.py
│   ├── budget.py
│   ├── explanation.py
│   ├── incremental_graph.py
│   ├── models.py
│   ├── reporting.py
│   └── watch.py
├── ui/                        # Web Surveillance Interface
│   ├── server.py              # FastAPI server & REST API
│   ├── templates/index.html   # Single-page web dashboard
│   └── static/
│       ├── css/style.css      # Dark-mode glassmorphism design system
│       └── js/
│           ├── app.js         # Frontend app logic & Chart.js trends
│           └── graph.js       # Vis.js interactive graph visualizer
├── tests/                     # Comprehensive Pytest Suite
│   ├── test_adversarial.py
│   ├── test_atlas.py
│   ├── test_explain.py
│   ├── test_human_gate.py
│   ├── test_memory.py
│   ├── test_monitor.py
│   └── test_watch.py
├── outputs/                   # Generated reports & decision traces
├── requirements.txt
├── README.md
└── run.py                     # Unified CLI Entry Point
```

---

## Installation & Setup

1. **Prerequisites**: Python 3.10+
2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## Usage Guide

### 1. Run Complete 12-Cut Surveillance Period
Executes all 12 cuts in sequence, applies incremental deltas/corrections, intercepts adversarial anomalies, and exports `outputs/surveillance_report.md` and `outputs/decision_trace.json`:
```bash
python run.py --mode full
```

### 2. Launch Interactive Web Interface
Launches the web dashboard on `http://localhost:8000`:
```bash
python run.py --mode ui --port 8000
```
**UI Features**:
- **Dashboard**: Live KPIs, current cut metrics, findings and actions.
- **12-Cut Timeline & Trends**: Interactive cut buttons and Chart.js trend graphs.
- **Study Graph Explorer**: Vis.js interactive knowledge graph visualization.
- **Findings & Subjects**: Filterable list of all clinical findings.
- **Human Gate**: Medical monitor escalation queue with APPROVED, REJECTED, and CLARIFY states.
- **Adversarial & Site Risk**: Integrity anomaly feed and site risk profiling.
- **Audit Decision Trace & Explain Modal**: Drill down into any decision with full evidence citation.
- **Surveillance Report**: Rendered executive report with print/PDF export.

### 3. Run Single Cut Cycle
```bash
python run.py --mode cut --cut 5
```

### 4. Explain Any Decision from Audit Trace
```bash
python run.py --mode explain --explain DEC-DETECT-CUT1
```

### 5. Run All Unit Tests
```bash
python run.py --mode test
```
or directly:
```bash
python -m pytest -v
```
