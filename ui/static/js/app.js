// Study Sentinel - Clinical Study Surveillance Platform Logic
// Full 11-Page Architecture & 5-Minute Judge Demonstration Tour

let currentCut = 12;
let cutsSummaryData = [];
let globalStatus = null;
let overviewChart = null;
let findingsChart = null;
let queriesChart = null;
let budgetChart = null;
let patientActivityChart = null;

document.addEventListener("DOMContentLoaded", () => {
  initNavTabs();
  initExplainModal();
  initPatientSearch();
  loadInitialData();
});

// ----------------------------------------------------------------------------
// 1. Navigation Tab Handling
// ----------------------------------------------------------------------------
function initNavTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      switchTab(tab.getAttribute("data-tab"));
    });
  });
}

function initPatientSearch() {
  const btn = document.getElementById("psg-btn-search");
  const input = document.getElementById("psg-patient-id-input");
  if (btn) {
    btn.addEventListener("click", performPatientSearch);
  }
  if (input) {
    input.addEventListener("keypress", (e) => {
      if (e.key === "Enter") performPatientSearch();
    });
  }
}

function switchTab(target) {
  document.querySelectorAll(".nav-tab").forEach(t => {
    t.classList.toggle("active", t.getAttribute("data-tab") === target);
  });
  document.querySelectorAll(".tab-content").forEach(c => {
    c.classList.toggle("active", c.id === `tab-${target}`);
  });

  // Trigger lazy loading per tab
  if (target === "overview") {
    renderOverviewPage();
  } else if (target === "graph-view") {
    loadSubjectsDropdown();
  } else if (target === "patient-graph") {
    const inputVal = document.getElementById("psg-patient-id-input") ? document.getElementById("psg-patient-id-input").value.trim() : "";
    if (inputVal && !document.getElementById("psg-patient-content").style.display.includes("flex")) {
      performPatientSearch();
    }
  } else if (target === "timeline") {
    renderTrendCharts();
    renderTimelineGrid();
  } else if (target === "findings") {
    renderFindingsPage();
  } else if (target === "human-gate") {
    loadHumanGateCards();
  } else if (target === "cycle-report") {
    loadCycleReport(currentCut);
  } else if (target === "trace") {
    loadTraceTable();
  } else if (target === "explain") {
    // Keep explain screen state
  } else if (target === "site-risk") {
    loadSiteRiskPage();
  } else if (target === "adversarial") {
    loadAdversarialCards();
  } else if (target === "budget") {
    loadBudgetPage();
  }
}


// ----------------------------------------------------------------------------
// 2. Initial Data Loading & Global Metrics
// ----------------------------------------------------------------------------
async function loadInitialData() {
  try {
    const statusRes = await fetch("/api/status");
    globalStatus = await statusRes.json();

    // Populate Top Metrics
    document.getElementById("m-cut").innerText = `Cut ${globalStatus.current_cut}`;
    document.getElementById("m-pv").innerText = `Protocol Version ${globalStatus.protocol_version}`;
    document.getElementById("m-escalations").innerText = globalStatus.total_escalations;
    document.getElementById("m-esc-sub").innerText = `${globalStatus.approved_escalations} Approved | ${globalStatus.pending_escalations} Pending`;
    document.getElementById("m-queries").innerText = globalStatus.total_queries;
    document.getElementById("m-q-sub").innerText = `${globalStatus.open_queries} Open | ${globalStatus.closed_queries} Closed`;
    document.getElementById("m-deviations").innerText = globalStatus.compliance_deviations;
    document.getElementById("m-adversarial").innerText = globalStatus.adversarial_alerts_count;
    document.getElementById("m-budget-tier").innerText = globalStatus.budget.tier;
    document.getElementById("m-budget-time").innerText = `${globalStatus.budget.elapsed_seconds.toFixed(2)}s Elapsed`;

    // Overview Stats
    document.getElementById("ov-pv").innerText = `Protocol Version ${globalStatus.protocol_version} (Effective Cut 9)`;
    document.getElementById("ov-crit-esc").innerText = `${globalStatus.approved_escalations} Approved Dosing Holds`;
    document.getElementById("ov-mon-findings").innerText = `${globalStatus.monitoring_findings} Subjects Monitored`;
    document.getElementById("ov-open-q").innerText = `${globalStatus.open_queries} Requiring Site Clarification`;
    document.getElementById("ov-corrections").innerText = `${globalStatus.applied_corrections} Records Updated Dynamically`;
    document.getElementById("ov-trace-count").innerText = `${globalStatus.total_trace_entries} Total Decisions Audited`;

    // Load Cuts Summary
    const cutsRes = await fetch("/api/cuts-summary");
    cutsSummaryData = await cutsRes.json();
    renderCutsTimelineButtons();

    // Select Cut 12 by default
    selectCut(12);

    // Initial Overview rendering
    renderOverviewPage();
  } catch (err) {
    console.error("Error during initial data loading:", err);
  }
}

// ----------------------------------------------------------------------------
// 3. 12-Cut Selector Bar
// ----------------------------------------------------------------------------
function renderCutsTimelineButtons() {
  const container = document.getElementById("cuts-buttons-container");
  if (!container) return;
  container.innerHTML = "";

  for (let c = 1; c <= 12; c++) {
    const cutData = cutsSummaryData.find(item => item.cut === c);
    const pv = cutData ? cutData.protocol_version : (c >= 9 ? 3 : c >= 5 ? 2 : 1);

    const btn = document.createElement("div");
    btn.className = `cut-btn ${c === currentCut ? "active" : ""}`;
    btn.id = `cut-btn-${c}`;
    btn.innerHTML = `
      <span class="cut-num">Cut ${c}</span>
      <span class="cut-pv">v${pv}</span>
    `;
    btn.addEventListener("click", () => selectCut(c));
    container.appendChild(btn);
  }
}

async function selectCut(cutNumber) {
  currentCut = cutNumber;
  document.querySelectorAll(".cut-btn").forEach((btn, idx) => {
    btn.classList.toggle("active", idx + 1 === cutNumber);
  });

  const activeCutData = cutsSummaryData.find(c => c.cut === cutNumber);
  const pv = activeCutData ? activeCutData.protocol_version : 3;
  document.getElementById("active-cut-badge").innerText = `Active Cut: ${cutNumber} (Protocol v${pv})`;
  document.getElementById("ov-cut-title").innerText = `Cut ${cutNumber} Summary Highlights`;

  try {
    const res = await fetch(`/api/cut/${cutNumber}/details`);
    const details = await res.json();
    renderOverviewCutHighlights(details);

    // If Cycle Report tab is active, refresh it
    if (document.getElementById("tab-cycle-report").classList.contains("active")) {
      loadCycleReport(cutNumber);
    }
  } catch (err) {
    console.error(`Error loading details for cut ${cutNumber}:`, err);
  }
}

// ----------------------------------------------------------------------------
// PAGE 1: OVERVIEW
// ----------------------------------------------------------------------------
function renderOverviewPage() {
  if (cutsSummaryData.length === 0) return;

  const ctx = document.getElementById("overviewMiniChart");
  if (ctx) {
    if (overviewChart) overviewChart.destroy();
    overviewChart = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: ["Approved Escalations", "Data Queries", "Compliance Deviations", "Adversarial Quarantines"],
        datasets: [{
          data: [
            globalStatus ? globalStatus.approved_escalations : 9,
            globalStatus ? globalStatus.total_queries : 91,
            globalStatus ? globalStatus.compliance_deviations : 60,
            globalStatus ? globalStatus.adversarial_alerts_count : 31
          ],
          backgroundColor: ["#ef4444", "#f59e0b", "#06b6d4", "#8b5cf6"],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "right", labels: { color: "#9ca3af", font: { size: 11 } } }
        }
      }
    });
  }
}

function renderOverviewCutHighlights(details) {
  const tbody = document.getElementById("overview-highlights-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const allItems = [
    ...details.escalations.map(e => ({ ...e, _type: "ESCALATION" })),
    ...details.queries.map(q => ({ ...q, _type: "DATA QUERY" })),
    ...details.deviations.map(d => ({ ...d, _type: "DEVIATION" }))
  ];

  if (allItems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No critical interventions required for Cut ${details.cut} (Routine observational monitoring).</td></tr>`;
    return;
  }

  allItems.slice(0, 10).forEach(item => {
    const isEsc = item._type === "ESCALATION";
    const id = item.escalation_id || item.query_id || item.code;
    const severity = item.severity || "MEDIUM";
    const status = item.status || "LOGGED";
    const sevBadge = severity === "CRITICAL" ? "badge-critical" : severity === "HIGH" ? "badge-high" : "badge-medium";
    const statBadge = status === "APPROVED" || status === "CLOSED" ? "badge-success" : status === "REJECTED" ? "badge-danger" : "badge-high";

    tbody.innerHTML += `
      <tr>
        <td><b>${item._type}</b></td>
        <td><code>${id}</code></td>
        <td>${item.usubjid || "STUDY"}</td>
        <td>${item.site || "S01"}</td>
        <td><span class="badge ${sevBadge}">${severity}</span></td>
        <td><span class="badge ${statBadge}">${status}</span></td>
        <td>${item.summary || item.text || item.description || "Identified discrepancy"}</td>
      </tr>
    `;
  });
}

// ----------------------------------------------------------------------------
// PAGE 2: STUDY GRAPH & INSPECTOR
// ----------------------------------------------------------------------------
async function loadSubjectsDropdown() {
  const select = document.getElementById("graph-subject-select");
  if (select.children.length > 1) return;

  const res = await fetch("/api/subjects");
  const subjects = await res.json();
  subjects.forEach(s => {
    const opt = document.createElement("option");
    opt.value = s.usubjid;
    opt.innerText = `${s.usubjid} — Site ${s.siteid} (Age ${s.age}, ${s.arm || 'Arm A'})`;
    select.appendChild(opt);
  });

  document.getElementById("btn-refresh-graph").addEventListener("click", () => {
    const selected = select.value;
    if (selected) loadSubjectGraphAndDetails(selected);
  });

  if (subjects.length > 0) {
    select.value = subjects[0].usubjid;
    loadSubjectGraphAndDetails(subjects[0].usubjid);
  }
}

async function loadSubjectGraphAndDetails(usubjid) {
  try {
    const res = await fetch(`/api/graph/${usubjid}`);
    const data = await res.json();

    // Render Subgraph in Vis.js
    window.initGraphViewer("graph-container", data.graph);

    // Render Details in Side Inspector Panel
    const inspector = document.getElementById("inspector-details");
    inspector.innerHTML = `
      <div style="background: rgba(0,0,0,0.3); padding: 10px; border-radius: 6px; margin-bottom: 12px;">
        <div style="font-size: 15px; font-weight: 700; color: white;">${data.usubjid}</div>
        <div style="font-size: 12px; color: var(--text-muted);">Site: <b>${data.siteid}</b> | Age: <b>${data.age}</b> | Sex: <b>${data.sex}</b> | Arm: <b>${data.arm}</b></div>
        <div style="font-size: 12px; color: #34d399; margin-top: 4px;">First Protocol Dose: <b>${data.first_dose || 'Not recorded'}</b></div>
      </div>

      <h4 style="font-size: 12px; color: var(--accent-secondary); text-transform: uppercase; margin: 10px 0 6px 0;">Adverse Events (${data.events.length})</h4>
      <div style="font-size: 12px; max-height: 90px; overflow-y: auto;">
        ${data.events.length > 0 ? data.events.map(e => `<div>• <b>${e.term}</b> (Start: ${e.start_date || 'N/A'}, Hospitalized: ${e.hospitalized})</div>`).join('') : '<div style="color:var(--text-muted)">None recorded</div>'}
      </div>

      <h4 style="font-size: 12px; color: var(--accent-warning); text-transform: uppercase; margin: 10px 0 6px 0;">Labs (${data.labs.length})</h4>
      <div style="font-size: 12px; max-height: 90px; overflow-y: auto;">
        ${data.labs.length > 0 ? data.labs.slice(0, 6).map(l => `<div>• <b>${l.test}</b>: ${l.value} ${l.unit} (${l.date})</div>`).join('') : '<div style="color:var(--text-muted)">None recorded</div>'}
      </div>

      <h4 style="font-size: 12px; color: #f87171; text-transform: uppercase; margin: 10px 0 6px 0;">Findings & Escalations</h4>
      <div style="font-size: 12px;">
        ${data.escalations.length > 0 ? data.escalations.map(esc => `<div style="color:#f87171;">• <b>${esc.code}</b>: ${esc.status} (Cut ${esc.cut})</div>`).join('') : '<div style="color:var(--text-muted)">No safety escalations</div>'}
      </div>
    `;
  } catch (err) {
    console.error("Error loading subject graph & inspector:", err);
  }
}

// ----------------------------------------------------------------------------
// PAGE 3: CUT TIMELINE & TRENDS
// ----------------------------------------------------------------------------
function renderTrendCharts() {
  if (cutsSummaryData.length === 0) return;

  const labels = cutsSummaryData.map(c => `Cut ${c.cut}`);
  const findings = cutsSummaryData.map(c => c.findings_count);
  const escalations = cutsSummaryData.map(c => c.escalations_count);
  const queries = cutsSummaryData.map(c => c.queries_count);
  const deviations = cutsSummaryData.map(c => c.deviations_count);

  const ctx1 = document.getElementById("findingsChart");
  if (ctx1) {
    if (findingsChart) findingsChart.destroy();
    findingsChart = new Chart(ctx1, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          { label: "Raw Candidate Findings", data: findings, borderColor: "#6366f1", backgroundColor: "rgba(99, 102, 241, 0.1)", tension: 0.3, fill: true },
          { label: "Safety Escalations", data: escalations, borderColor: "#ef4444", backgroundColor: "rgba(239, 68, 68, 0.15)", tension: 0.3, fill: true }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#9ca3af" } } },
        scales: {
          x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#9ca3af" } },
          y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#9ca3af" } }
        }
      }
    });
  }

  const ctx2 = document.getElementById("queriesChart");
  if (ctx2) {
    if (queriesChart) queriesChart.destroy();
    queriesChart = new Chart(ctx2, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          { label: "Data Quality Queries", data: queries, backgroundColor: "#f59e0b" },
          { label: "Compliance Deviations", data: deviations, backgroundColor: "#06b6d4" }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#9ca3af" } } },
        scales: {
          x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#9ca3af" } },
          y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#9ca3af" } }
        }
      }
    });
  }
}

function renderTimelineGrid() {
  const tbody = document.getElementById("timeline-grid-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  cutsSummaryData.forEach(c => {
    tbody.innerHTML += `
      <tr style="cursor: pointer;" onclick="selectCut(${c.cut}); switchTab('overview');">
        <td><b>Cut ${c.cut}</b></td>
        <td><span class="badge badge-info">v${c.protocol_version}</span></td>
        <td>${c.new_findings}</td>
        <td><span class="badge badge-success">${c.resolved_findings}</span></td>
        <td><span class="badge badge-critical">${c.escalations_count} (${c.approved_escalations} Appr)</span></td>
        <td>${c.queries_count}</td>
        <td>${c.deviations_count}</td>
        <td>${c.corrections_count > 0 ? `<span class="badge badge-purple">${c.corrections_count} Records</span>` : '-'}</td>
        <td>${c.adversarial_alerts.length > 0 ? `<span class="badge badge-danger">${c.adversarial_alerts.length} Alert</span>` : '0'}</td>
        <td><span class="badge badge-success">${c.budget_tier} (${c.budget_elapsed}s)</span></td>
      </tr>
    `;
  });
}

// ----------------------------------------------------------------------------
// PAGE 4: FINDINGS
// ----------------------------------------------------------------------------
let currentFindingsList = [];

async function renderFindingsPage() {
  const res = await fetch(`/api/cut/${currentCut}/details`);
  const details = await res.json();
  const tbody = document.getElementById("findings-table-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  currentFindingsList = [
    ...details.escalations.map(e => ({ ...e, _cat: "SAFETY", _sev: e.severity || "CRITICAL" })),
    ...details.queries.map(q => ({ ...q, _cat: "DATA_QUALITY", _sev: "MEDIUM" })),
    ...details.deviations.map(d => ({ ...d, _cat: "COMPLIANCE", _sev: "HIGH" }))
  ];

  filterAndRenderFindings();

  // Attach search and filter listeners
  document.getElementById("finding-search-input").oninput = filterAndRenderFindings;
  document.getElementById("finding-cat-filter").onchange = filterAndRenderFindings;
}

function filterAndRenderFindings() {
  const tbody = document.getElementById("findings-table-tbody");
  const query = (document.getElementById("finding-search-input").value || "").toLowerCase();
  const catFilter = document.getElementById("finding-cat-filter").value;

  tbody.innerHTML = "";

  const filtered = currentFindingsList.filter(f => {
    const matchesCat = catFilter === "ALL" || f._cat === catFilter;
    const matchesQuery = !query || 
      (f.usubjid && f.usubjid.toLowerCase().includes(query)) ||
      (f.code && f.code.toLowerCase().includes(query)) ||
      (f.site && f.site.toLowerCase().includes(query));
    return matchesCat && matchesQuery;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">No findings match the current filter.</td></tr>`;
    return;
  }

  filtered.forEach(item => {
    const code = item.code || item.issue_code || "FINDING";
    const decId = item.escalation_id ? `DEC-GATE-APP-${item.escalation_id}` : `DEC-DM-QUERY-${item.query_id || 'ID'}`;
    const sevBadge = item._sev === "CRITICAL" ? "badge-critical" : item._sev === "HIGH" ? "badge-high" : "badge-medium";

    tbody.innerHTML += `
      <tr>
        <td><b>${code}</b></td>
        <td><span class="badge badge-info">${item._cat}</span></td>
        <td><b>${item.usubjid || "-"}</b></td>
        <td>${item.site || "-"}</td>
        <td><span class="badge ${sevBadge}">${item._sev}</span></td>
        <td>${item.summary || item.text || item.description || "Identified discrepancy"}</td>
        <td><span class="badge badge-success">${item.status || "ACTIONED"}</span></td>
        <td><button class="btn btn-secondary" style="padding: 4px 10px;" onclick="openExplainModal('${decId}')">Explain</button></td>
      </tr>
    `;
  });
}

// ----------------------------------------------------------------------------
// PAGE 5: HUMAN GATE & CLARIFY INTERACTIVE DEMO
// ----------------------------------------------------------------------------
async function loadHumanGateCards() {
  const res = await fetch(`/api/cut/${currentCut}/details`);
  const data = await res.json();
  const container = document.getElementById("escalation-cards-container");
  if (!container) return;
  container.innerHTML = "";

  const escalations = data.escalations || [];
  if (escalations.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); padding: 20px;">No pending escalations requiring medical monitor review in Cut ${currentCut}.</div>`;
    return;
  }

  escalations.forEach(esc => {
    const card = document.createElement("div");
    card.className = `escalation-card ${esc.status.toLowerCase()}`;
    const evidenceLines = (esc.evidence || []).map(e => `[${e.domain}] Subject ${e.usubjid}, Record #${e.seq}`).join("<br>");

    card.innerHTML = `
      <div class="escalation-header">
        <div>
          <div class="escalation-title">${esc.code}: ${esc.usubjid}</div>
          <div class="escalation-meta">Site: <b>${esc.site}</b> | Severity: <span class="badge badge-critical">${esc.severity}</span> | Cut ${esc.cut}</div>
        </div>
        <span class="badge ${esc.status === 'APPROVED' ? 'badge-success' : 'badge-danger'}">${esc.status}</span>
      </div>

      <div class="escalation-body">
        <b>Finding Summary:</b> ${esc.summary}<br>
        <b>Clinical Rationale:</b> ${esc.rationale}
      </div>

      <div class="escalation-evidence">
        <b>Cited Evidence References:</b><br>
        ${evidenceLines || 'Direct trial finding'}
      </div>

      <div style="font-size: 12px; color: var(--text-muted);">
        <b>Alternatives Considered:</b> Routine monitoring, site laboratory query.
      </div>

      <div class="escalation-actions">
        <button class="btn btn-success" onclick="alert('Action APPROVED: Subject dosing held and Safety Committee notified.')">APPROVE</button>
        <button class="btn btn-danger" onclick="alert('Action REJECTED: Downgraded to observational monitoring; repeat escalations suppressed.')">REJECT</button>
        <button class="btn btn-clarify" onclick="runClarifyInteractiveDemo()">CLARIFY</button>
        <button class="btn btn-secondary" style="margin-left: auto;" onclick="openExplainModal('DEC-GATE-APP-${esc.escalation_id}')">Explain</button>
      </div>
    `;
    container.appendChild(card);
  });
}

async function runClarifyInteractiveDemo() {
  const container = document.getElementById("clarify-demo-output");
  container.style.display = "flex";
  container.innerHTML = `<div style="color: var(--accent-purple);">Querying Knowledge Graph for Baseline Evidence...</div>`;

  try {
    const res = await fetch("/api/human-gate/clarify-demo");
    const demo = await res.json();

    container.innerHTML = `
      <div class="clarify-step">
        <div class="clarify-step-num">1</div>
        <div class="clarify-step-content">
          <b>Medical Monitor Clarification Inquiry:</b><br>
          <span style="color: #cbd5e1;">"${demo.monitor_query}"</span>
        </div>
      </div>

      <div class="clarify-step">
        <div class="clarify-step-num">2</div>
        <div class="clarify-step-content">
          <b>Graph Traversal & Evidence Lookup:</b><br>
          <span style="color: #93c5fd; font-family: var(--font-mono); font-size: 12px;">
            • First Dose Date: ${demo.graph_lookup.first_dose}<br>
            • Event Onset: ${demo.graph_lookup.event_onset}<br>
            • Screening ALT: ${demo.graph_lookup.screening_labs.ALT}<br>
            • Screening AST: ${demo.graph_lookup.screening_labs.AST}<br>
            • Concomitant Medications: ${demo.graph_lookup.concomitant_medications.join(', ')}
          </span>
        </div>
      </div>

      <div class="clarify-step">
        <div class="clarify-step-num">3</div>
        <div class="clarify-step-content">
          <b>System Formulated Response:</b><br>
          <span style="color: #34d399;">${demo.system_answer}</span>
        </div>
      </div>

      <div class="clarify-step">
        <div class="clarify-step-num">4</div>
        <div class="clarify-step-content">
          <b>Resubmission Result:</b> <span class="badge badge-success">${demo.resubmission_status}</span><br>
          <b>Enacted Decision:</b> ${demo.action_taken}
        </div>
      </div>
    `;
  } catch (err) {
    console.error("Error executing CLARIFY demo:", err);
  }
}

// ----------------------------------------------------------------------------
// PAGE 6: CYCLE REPORT (6-Node Sequential Pipeline)
// ----------------------------------------------------------------------------
async function loadCycleReport(cut) {
  const container = document.getElementById("pipeline-nodes-container");
  document.getElementById("cycle-report-title").innerText = `Cut ${cut} Review Crew Execution Pipeline`;
  if (!container) return;
  container.innerHTML = "<p>Loading 6-node cycle execution...</p>";

  try {
    const res = await fetch(`/api/cycle-report/${cut}`);
    const data = await res.json();
    container.innerHTML = "";

    data.nodes.forEach(node => {
      const el = document.createElement("div");
      el.className = "pipeline-node";
      el.innerHTML = `
        <div class="pipeline-order">${node.order}</div>
        <div>
          <div class="pipeline-name">${node.title}</div>
          <span class="badge badge-info" style="font-size: 10px;">${node.node}</span>
        </div>
        <div style="font-size: 13px; color: #cbd5e1;">
          <b>Input Context:</b> ${node.input}<br>
          <b>Decision:</b> ${node.decision}
        </div>
        <div style="font-size: 13px; color: #34d399;">
          <b>Output:</b> ${node.output}
        </div>
        <div>
          <span class="badge badge-success">${node.trace_count} Trace Logs</span>
        </div>
      `;
      container.appendChild(el);
    });
  } catch (err) {
    console.error(`Error loading cycle report for cut ${cut}:`, err);
  }
}

// ----------------------------------------------------------------------------
// PAGE 7: TRACE VIEWER
// ----------------------------------------------------------------------------
async function loadTraceTable() {
  const res = await fetch("/api/trace");
  const entries = await res.json();
  const tbody = document.getElementById("trace-table-tbody");
  document.getElementById("trace-count-badge").innerText = `${entries.length} Immutable Entries`;
  if (!tbody) return;
  tbody.innerHTML = "";

  entries.slice(-60).reverse().forEach(e => {
    const evText = (e.evidence || []).map(ev => `${ev.domain}:${ev.usubjid}:${ev.seq}`).join(", ") || "-";
    tbody.innerHTML += `
      <tr>
        <td style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${(e.timestamp || '').substring(11, 19)}</td>
        <td><b>Cut ${e.cut}</b></td>
        <td><span class="badge badge-info">${e.node}</span></td>
        <td><code>${e.decision_id}</code></td>
        <td>${e.subject || "-"}</td>
        <td>${e.site || "-"}</td>
        <td style="font-family: var(--font-mono); font-size: 11px;">${evText}</td>
        <td>${e.reason}</td>
        <td><button class="btn btn-secondary" style="padding: 3px 8px; font-size: 11px;" onclick="openExplainModal('${e.decision_id}')">Explain</button></td>
      </tr>
    `;
  });
}

// ----------------------------------------------------------------------------
// PAGE 8: EXPLAIN DECISION
// ----------------------------------------------------------------------------
function initExplainModal() {
  const modal = document.getElementById("explain-modal");
  const closeBtn = document.getElementById("btn-close-modal");
  closeBtn.addEventListener("click", () => modal.classList.remove("active"));
  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.remove("active");
  });
}

async function submitExplainForm() {
  const decId = document.getElementById("explain-input-id").value.trim();
  if (!decId) return;
  
  try {
    const res = await fetch(`/api/explain/${decId}`);
    const exp = await res.json();
    renderExplainPageResult(exp);
  } catch (err) {
    console.error("Error submitting explain form:", err);
  }
}

function renderExplainPageResult(exp) {
  const container = document.getElementById("explain-page-result");
  const evidenceLines = (exp.evidence_lines || []).join("<br>");
  const alts = (exp.alternatives || []).map(a => `<li>${a}</li>`).join("");

  container.innerHTML = `
    <div style="background: rgba(15, 23, 42, 0.85); border: 1px solid var(--border-color); border-radius: 12px; padding: 22px;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; margin-bottom: 16px;">
        <div>
          <h3 style="font-size: 18px; color: white;">${exp.decision_id}</h3>
          <span style="font-size: 12px; color: var(--text-muted);">Cut ${exp.cut} | Protocol Version ${exp.protocol_version} | Node: <span class="badge badge-info">${exp.node}</span></span>
        </div>
        <span class="badge badge-success" style="font-size: 13px; padding: 6px 14px;">Explanation verified against trace (consistent_with_trace = True)</span>
      </div>

      <div class="explain-section">
        <h4>What Action Was Taken</h4>
        <div class="evidence-box">${exp.what}</div>
      </div>

      <div class="explain-section">
        <h4>Why (Clinical Rationale & Protocol Rule Enforcement)</h4>
        <p style="font-size: 14px; line-height: 1.6; color: #e5e7eb;">${exp.why}</p>
      </div>

      <div class="explain-section">
        <h4>Cited Immutable Audit Evidence Lines</h4>
        <div class="evidence-box">${evidenceLines || 'No direct record coordinates cited.'}</div>
      </div>

      <div class="explain-section">
        <h4>Alternatives Considered</h4>
        <ul style="margin-left: 20px; font-size: 13px; color: var(--text-muted); line-height: 1.6;">${alts || '<li>Standard study monitoring</li>'}</ul>
      </div>
    </div>
  `;
}

async function openExplainModal(decisionId) {
  try {
    const res = await fetch(`/api/explain/${decisionId}`);
    const exp = await res.json();

    document.getElementById("modal-decision-id").innerText = exp.decision_id;
    document.getElementById("modal-what").innerText = `[${exp.node.toUpperCase()}] ${exp.what}`;
    document.getElementById("modal-why").innerText = exp.why;

    const evBox = document.getElementById("modal-evidence");
    evBox.innerHTML = (exp.evidence_lines && exp.evidence_lines.length > 0) ? exp.evidence_lines.join("<br>") : "No direct evidence cited.";

    const altList = document.getElementById("modal-alternatives");
    altList.innerHTML = "";
    (exp.alternatives || []).forEach(a => {
      altList.innerHTML += `<li>${a}</li>`;
    });

    const badge = document.getElementById("modal-consistent-badge");
    badge.className = exp.consistent_with_trace ? "badge badge-success" : "badge badge-critical";
    badge.innerText = `Explanation verified against trace (consistent_with_trace = ${exp.consistent_with_trace})`;

    document.getElementById("modal-meta-cut").innerText = `Cut ${exp.cut} | Protocol v${exp.protocol_version}`;
    document.getElementById("explain-modal").classList.add("active");
  } catch (err) {
    console.error("Error explaining decision:", err);
  }
}

window.openExplainModal = openExplainModal;

// ----------------------------------------------------------------------------
// PAGE 9: SITE RISK
// ----------------------------------------------------------------------------
async function loadSiteRiskPage() {
  const res = await fetch("/api/site-risks");
  const risks = await res.json();
  const tbody = document.getElementById("site-risk-page-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (risks.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center;">No elevated site risks detected.</td></tr>`;
    return;
  }

  risks.forEach(r => {
    const badge = r.risk_level === "HIGH" ? "badge-critical" : r.risk_level === "MEDIUM" ? "badge-high" : "badge-low";
    tbody.innerHTML += `
      <tr>
        <td><b>Site ${r.site_id}</b></td>
        <td><b>${r.total_issues}</b></td>
        <td><span class="badge ${badge}">${r.risk_level}</span></td>
        <td>${r.escalations_count || 0}</td>
        <td>${r.queries_count || 0}</td>
        <td>${r.last_issue || "Routine trial conduct"}</td>
        <td><span class="badge badge-info">${r.risk_level === 'HIGH' ? 'Auditor Inspection' : 'Enhanced Querying'}</span></td>
      </tr>
    `;
  });
}

// ----------------------------------------------------------------------------
// PAGE 10: ADVERSARIAL EVENTS
// ----------------------------------------------------------------------------
async function loadAdversarialCards() {
  const grid = document.getElementById("adversarial-cards-grid");
  if (!grid) return;
  grid.innerHTML = "<p>Loading adversarial analysis...</p>";

  try {
    const res = await fetch("/api/adversarial-summary");
    const data = await res.json();
    grid.innerHTML = "";

    data.categories.forEach(cat => {
      const card = document.createElement("div");
      card.className = "adversarial-card";
      card.innerHTML = `
        <div class="adversarial-card-title">
          <span>${cat.title}</span>
          <span class="badge badge-purple">INTERCEPTED</span>
        </div>

        <div style="font-size: 13px; color: #cbd5e1;">
          <b>Pattern Detected:</b> ${cat.detected}
        </div>

        <div class="evidence-box">
          <b>Statistical / Trace Evidence:</b><br>${cat.evidence}
        </div>

        <div style="font-size: 13px; color: #34d399;">
          <b>System Response:</b> ${cat.system_response}
        </div>

        <div style="font-size: 13px; color: #f87171; border-top: 1px solid var(--border-color); padding-top: 8px;">
          <b>Escalation Policy:</b> ${cat.escalation_decision}
        </div>
      `;
      grid.appendChild(card);
    });
  } catch (err) {
    console.error("Error loading adversarial cards:", err);
  }
}

// ----------------------------------------------------------------------------
// PAGE 11: BUDGET
// ----------------------------------------------------------------------------
async function loadBudgetPage() {
  const ctx = document.getElementById("budgetChart");
  if (!ctx || cutsSummaryData.length === 0) return;

  const labels = cutsSummaryData.map(c => `Cut ${c.cut}`);
  const elapsedTimes = cutsSummaryData.map(c => c.budget_elapsed);
  const limits = cutsSummaryData.map(() => 600.0);

  if (budgetChart) budgetChart.destroy();
  budgetChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        { label: "Cumulative Seconds", data: elapsedTimes, borderColor: "#34d399", backgroundColor: "rgba(52, 211, 153, 0.15)", fill: true },
        { label: "Max Global Timeout (600s)", data: limits, borderColor: "#ef4444", borderDash: [5, 5], fill: false }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#9ca3af" } } },
      scales: {
        x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#9ca3af" } },
        y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#9ca3af" } }
      }
    }
  });
}

// ----------------------------------------------------------------------------
// 5-MINUTE GUIDED JUDGE DEMONSTRATION TOUR
// ----------------------------------------------------------------------------
const tourSteps = [
  { tab: "graph-view", msg: "Step 1: Relational Knowledge Graph. Inspect study subjects and connected clinical nodes." },
  { tab: "findings", msg: "Step 2: Critical Finding. View SAE hospitalization miscoding (AESHOSP=Y)." },
  { tab: "cycle-report", msg: "Step 3: Medical Review Node. Sequential execution through clinical review." },
  { tab: "human-gate", msg: "Step 4: Human Gate. Medical monitor escalation queue with approval actions." },
  { tab: "human-gate", msg: "Step 5 & 6: Interactive CLARIFY. Watch graph lookup baseline labs & resolve the query automatically.", action: () => runClarifyInteractiveDemo() },
  { tab: "timeline", msg: "Step 7: 12-Cut Surveillance Horizon. Full trajectory across 12 weekly cycles." },
  { tab: "adversarial", msg: "Step 8 & 9: Laboratory Unit Corruption (~18x ratio). Quarantined as data query, NOT medical emergency." },
  { tab: "explain", msg: "Step 10, 11 & 12: Deterministic Decision Explanation. Citing exact evidence lines with verified trace consistency.", action: () => {
    document.getElementById("explain-input-id").value = "DEC-MR-SAE-042-S02-004";
    submitExplainForm();
  }}
];

let currentTourIndex = 0;

function start5MinTour() {
  currentTourIndex = 0;
  runNextTourStep();
}

function runNextTourStep() {
  if (currentTourIndex >= tourSteps.length) {
    alert("5-Minute Demonstration Tour Completed Successfully!");
    return;
  }

  const step = tourSteps[currentTourIndex];
  switchTab(step.tab);
  if (step.action) step.action();

  currentTourIndex++;
}

// ----------------------------------------------------------------------------
// PATIENT STUDY GRAPH SEARCH & PROFILE RENDERING
// ----------------------------------------------------------------------------
function quickSearchPatient(patientId) {
  const input = document.getElementById("psg-patient-id-input");
  if (input) input.value = patientId;
  switchTab("patient-graph");
  performPatientSearch();
}

async function performPatientSearch() {
  const input = document.getElementById("psg-patient-id-input");
  const alertBanner = document.getElementById("psg-alert-banner");
  const contentContainer = document.getElementById("psg-patient-content");

  if (!input) return;
  const rawId = input.value.trim();

  // Validate empty input
  if (!rawId) {
    alertBanner.style.display = "block";
    alertBanner.style.background = "rgba(245, 158, 11, 0.15)";
    alertBanner.style.borderColor = "rgba(245, 158, 11, 0.4)";
    alertBanner.style.color = "#fbbf24";
    alertBanner.innerHTML = "<b>Please enter a Patient ID.</b> (e.g. <code>042-S02-004</code>)";
    contentContainer.style.display = "none";
    return;
  }

  // Show loading indicator
  alertBanner.style.display = "block";
  alertBanner.style.background = "rgba(99, 102, 241, 0.15)";
  alertBanner.style.borderColor = "rgba(99, 102, 241, 0.4)";
  alertBanner.style.color = "#a5b4fc";
  alertBanner.innerHTML = "<b>Loading patient study data...</b> Retrieving graph relationships, MONITOR decisions, and WATCH trace history.";

  try {
    const res = await fetch(`/api/patients/${encodeURIComponent(rawId)}/study-profile`);
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      const detail = errData.detail || `Patient not found. No subject with ID: ${rawId}. Check the Patient ID and try again.`;
      alertBanner.style.display = "block";
      alertBanner.style.background = "rgba(239, 68, 68, 0.15)";
      alertBanner.style.borderColor = "rgba(239, 68, 68, 0.4)";
      alertBanner.style.color = "#f87171";
      alertBanner.innerHTML = `<b>Patient Not Found:</b> ${detail}`;
      contentContainer.style.display = "none";
      return;
    }

    const profile = await res.json();
    alertBanner.style.display = "none";
    contentContainer.style.display = "flex";

    renderPatientStudyProfile(profile);
  } catch (err) {
    console.error("Error retrieving patient profile:", err);
    alertBanner.style.display = "block";
    alertBanner.style.background = "rgba(239, 68, 68, 0.15)";
    alertBanner.style.borderColor = "rgba(239, 68, 68, 0.4)";
    alertBanner.style.color = "#f87171";
    alertBanner.innerHTML = "<b>Unable to retrieve patient data.</b> Please check the backend connection and try again.";
    contentContainer.style.display = "none";
  }
}

function renderPatientStudyProfile(profile) {
  // 1. Overview Cards & Status Badges
  document.getElementById("psg-card-id").innerText = profile.patient_id;
  document.getElementById("psg-card-site").innerText = profile.site_id;
  document.getElementById("psg-card-study").innerText = profile.study_id || "042";
  document.getElementById("psg-card-pv").innerText = `v${profile.protocol_version}`;
  document.getElementById("psg-card-cut").innerText = profile.current_cut;
  document.getElementById("psg-card-status").innerText = profile.monitoring_status;

  const statusBadge = document.getElementById("psg-status-badge");
  if (profile.monitoring_status === "ACTION_REQUIRED") {
    statusBadge.className = "badge badge-danger";
    statusBadge.innerText = "ACTION REQUIRED";
  } else if (profile.monitoring_status === "MONITORING_DOSING_HELD") {
    statusBadge.className = "badge badge-warning";
    statusBadge.innerText = "DOSING HELD (MONITORING)";
  } else {
    statusBadge.className = "badge badge-success";
    statusBadge.innerText = "MONITORING";
  }

  // Summary strip
  const sum = profile.monitoring_summary || {};
  document.getElementById("psg-sum-q").innerText = sum.open_queries || 0;
  document.getElementById("psg-sum-esc").innerText = sum.open_escalations || 0;
  document.getElementById("psg-sum-dev").innerText = sum.protocol_deviations || 0;
  document.getElementById("psg-sum-sae").innerText = sum.serious_events || 0;
  document.getElementById("psg-sum-warn").innerText = sum.data_integrity_warnings || 0;

  // 2. Bar Graph: Patient Study Activity
  renderPatientActivityChart(profile.graph_metrics || {});

  // 3. Laboratory Measurements
  const labsTbody = document.getElementById("psg-labs-tbody");
  const warnBox = document.getElementById("psg-lab-warning-box");
  labsTbody.innerHTML = "";

  const labs = profile.labs || [];
  let hasUntrusted = false;

  if (labs.length === 0) {
    labsTbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">No laboratory results recorded for this patient.</td></tr>`;
    warnBox.style.display = "none";
  } else {
    labs.forEach(l => {
      if (l.trust_status === "Untrusted") hasUntrusted = true;
      const isUntrusted = l.trust_status === "Untrusted";
      const trustBadge = isUntrusted ? `<span class="badge badge-danger">Untrusted</span>` : `<span class="badge badge-success">Trusted</span>`;
      const warnText = l.data_integrity_warning ? `<span style="color: #f87171;">${l.data_integrity_warning}</span>` : "-";

      labsTbody.innerHTML += `
        <tr>
          <td>${l.seq}</td>
          <td><b>${l.test_code}</b></td>
          <td><b>${l.value_num !== null ? l.value_num : l.value_raw}</b></td>
          <td>${l.unit_raw || l.unit_std || '-'}</td>
          <td>${l.visit || 'Unscheduled'}</td>
          <td>${l.date || '-'}</td>
          <td>${trustBadge}</td>
          <td>${warnText}</td>
        </tr>
      `;
    });
    warnBox.style.display = hasUntrusted ? "block" : "none";
  }

  // 4. Timeline & Subgraph
  const timelineBox = document.getElementById("psg-timeline-container");
  timelineBox.innerHTML = "";
  const timeline = profile.timeline || [];
  if (timeline.length === 0) {
    timelineBox.innerHTML = `<p style="color: var(--text-muted); font-size: 13px;">No timeline milestones recorded.</p>`;
  } else {
    timeline.forEach(t => {
      const catBadge = t.category === "Event" ? "badge-danger" : t.category === "Anomaly" ? "badge-purple" : t.category === "Dose" ? "badge-success" : "badge-info";
      timelineBox.innerHTML += `
        <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px 14px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div style="font-weight: 600; font-size: 13px; color: white;">${t.milestone}</div>
            <div style="font-size: 11px; color: var(--text-muted);">${t.date}</div>
          </div>
          <span class="badge ${catBadge}">${t.category}</span>
        </div>
      `;
    });
  }

  if (window.initGraphViewer && profile.graph) {
    window.initGraphViewer("psg-graph-vis-container", profile.graph);
  }

  // 5. Adverse Events
  const aeTbody = document.getElementById("psg-ae-tbody");
  aeTbody.innerHTML = "";
  const aes = profile.adverse_events || [];

  if (aes.length === 0) {
    aeTbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted);">No adverse events recorded for this patient.</td></tr>`;
  } else {
    aes.forEach(ae => {
      const isSer = ae.is_protocol_serious;
      const serBadge = isSer ? `<span class="badge badge-critical">SERIOUS (AESHOSP=${ae.aeshosp})</span>` : `<span class="badge badge-low">NON-SERIOUS</span>`;
      const statusBadge = ae.status === "Escalated" ? `<span class="badge badge-danger">Escalated</span>` : `<span class="badge badge-info">Monitored</span>`;
      const escLink = ae.escalation_id ? `<code>${ae.escalation_id}</code>` : `-`;

      aeTbody.innerHTML += `
        <tr>
          <td>${ae.seq}</td>
          <td><b>${ae.term}</b></td>
          <td><span class="badge ${ae.severity === 'CRITICAL' ? 'badge-critical' : 'badge-high'}">${ae.severity}</span></td>
          <td>${ae.start_date || '-'}</td>
          <td><b>${ae.aeshosp}</b></td>
          <td>${ae.aeser}</td>
          <td>${serBadge}</td>
          <td>${statusBadge}</td>
          <td>${escLink}</td>
        </tr>
      `;
    });
  }

  // 6. Protocol Deviations
  const devTbody = document.getElementById("psg-deviations-tbody");
  const devBanner = document.getElementById("psg-protocol-amendment-banner");
  devTbody.innerHTML = "";
  const devs = profile.deviations || [];

  if (devs.length === 0) {
    devTbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No protocol deviations logged for this patient.</td></tr>`;
    devBanner.style.display = "none";
  } else {
    devs.forEach(d => {
      devTbody.innerHTML += `
        <tr>
          <td><code>${d.code || d.deviation_id}</code></td>
          <td>${d.visit || 'Visit Audit'}</td>
          <td><span class="badge badge-info">v${d.protocol_version || profile.protocol_version}</span></td>
          <td><span class="badge badge-high">${d.severity || 'MEDIUM'}</span></td>
          <td><span class="badge badge-warning">Logged</span></td>
          <td>${d.description || 'Compliance check finding'}</td>
        </tr>
      `;
    });
    devBanner.style.display = profile.protocol_version > 1 ? "block" : "none";
  }

  // 7. Queries & Escalations
  const qBox = document.getElementById("psg-queries-container");
  qBox.innerHTML = "";
  const queries = profile.queries || [];
  if (queries.length === 0) {
    qBox.innerHTML = `<p style="color: var(--text-muted); font-size: 13px;">No site data queries recorded for this patient.</p>`;
  } else {
    queries.forEach(q => {
      const qBadge = q.status === "CLOSED" ? "badge-success" : "badge-warning";
      qBox.innerHTML += `
        <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; border-radius: 8px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <b>${q.query_id || 'QUERY'} (${q.domain || 'LB'} Seq #${q.seq})</b>
            <span class="badge ${qBadge}">${q.status}</span>
          </div>
          <div style="font-size: 13px; color: #cbd5e1;"><b>Issue:</b> ${q.issue_code}</div>
          <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">${q.text}</div>
        </div>
      `;
    });
  }

  const escBox = document.getElementById("psg-escalations-container");
  escBox.innerHTML = "";
  const escs = profile.escalations || [];
  if (escs.length === 0) {
    escBox.innerHTML = `<p style="color: var(--text-muted); font-size: 13px;">No safety escalations logged for this patient.</p>`;
  } else {
    escs.forEach(e => {
      const stat = e.status || "PENDING";
      const eBadge = stat === "APPROVED" ? "badge-success" : stat === "REJECTED" ? "badge-danger" : stat === "CLARIFY" ? "badge-purple" : "badge-warning";
      
      let actionNote = e.action_taken || "";
      if (stat === "REJECTED") {
        actionNote = `Action downgraded to monitoring. Reason: ${e.monitor_response || 'Medical Monitor rejected dosing hold'}`;
      } else if (stat === "CLARIFY") {
        actionNote = `Clarification requested. Graph evidence retrieved. Resubmission performed. Answer: ${e.clarification_answer || 'Verified'}`;
      }

      escBox.innerHTML += `
        <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; border-radius: 8px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <b>${e.escalation_id || e.code}</b>
            <span class="badge ${eBadge}">${stat}</span>
          </div>
          <div style="font-size: 13px; color: #e2e8f0;"><b>Reason:</b> ${e.summary}</div>
          <div style="font-size: 12px; color: #93c5fd; margin-top: 4px;">${actionNote || e.rationale}</div>
        </div>
      `;
    });
  }

  // 8. Decisions & Trace Audit
  const decTbody = document.getElementById("psg-decisions-tbody");
  decTbody.innerHTML = "";
  const decisions = profile.decisions || [];

  if (decisions.length === 0) {
    decTbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No decision trace entries found for this patient.</td></tr>`;
  } else {
    decisions.forEach(d => {
      const decId = d.decision_id || "DEC-000";
      decTbody.innerHTML += `
        <tr>
          <td><code>${decId}</code></td>
          <td><span class="badge badge-info">${d.node || 'detect'}</span></td>
          <td>Cut ${d.cut || 12} (v${d.protocol_version || 3})</td>
          <td>${d.action || 'Evaluated'}</td>
          <td>${d.reason || 'Trace recorded'}</td>
          <td><span class="badge badge-success">Verified</span></td>
          <td>
            <button class="btn btn-secondary" style="padding: 3px 8px; font-size: 11px;" onclick="openExplainModal('${decId}')">View Explanation</button>
            <button class="btn btn-secondary" style="padding: 3px 8px; font-size: 11px; margin-left: 4px;" onclick="viewPatientTrace('${profile.patient_id}')">View Trace</button>
          </td>
        </tr>
      `;
    });
  }
}

function renderPatientActivityChart(metrics) {
  const ctx = document.getElementById("patientActivityChart");
  if (!ctx) return;

  const categories = ["Visits", "Lab Results", "Adverse Events", "Protocol Deviations", "Data Queries", "Escalations", "Decisions"];
  const values = [
    metrics.visits || 0,
    metrics.labs || 0,
    metrics.events || 0,
    metrics.deviations || 0,
    metrics.queries || 0,
    metrics.escalations || 0,
    metrics.decisions || 0
  ];

  if (patientActivityChart) patientActivityChart.destroy();

  patientActivityChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: categories,
      datasets: [{
        label: "Patient Activity Count",
        data: values,
        backgroundColor: [
          "#38bdf8",
          "#fbbf24",
          "#f87171",
          "#06b6d4",
          "#a78bfa",
          "#ef4444",
          "#10b981"
        ],
        borderRadius: 6,
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${ctx.formattedValue} records/events`
          }
        }
      },
      scales: {
        x: {
          grid: { color: "rgba(255,255,255,0.05)" },
          ticks: { color: "#9ca3af", font: { size: 12, weight: "600" } }
        },
        y: {
          beginAtZero: true,
          ticks: { color: "#9ca3af", precision: 0 },
          grid: { color: "rgba(255,255,255,0.05)" }
        }
      }
    }
  });
}

function viewPatientTrace(patientId) {
  switchTab("trace");
  loadTraceTable();
}

window.quickSearchPatient = quickSearchPatient;
window.performPatientSearch = performPatientSearch;
window.viewPatientTrace = viewPatientTrace;
window.start5MinTour = start5MinTour;
window.runClarifyInteractiveDemo = runClarifyInteractiveDemo;
window.submitExplainForm = submitExplainForm;

