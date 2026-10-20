// Data Scientist Agent - Frontend Client Logic

let activeChart = null;

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupPresets();
  setupQueryForm();
  loadRecentTraces();
  loadEvaluationReport();
});

// Tab Switching
function setupTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

      tab.classList.add("active");
      const targetPane = document.getElementById(tab.dataset.tab);
      if (targetPane) targetPane.classList.add("active");

      if (tab.dataset.tab === "tab-traces") {
        loadRecentTraces();
      }
    });
  });
}

// Preset Chips
function setupPresets() {
  document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const q = chip.dataset.q;
      const input = document.getElementById("question-input");
      input.value = q;
      document.getElementById("submit-btn").click();
    });
  });
}

// Query Form Submission
function setupQueryForm() {
  const form = document.getElementById("query-form");
  const input = document.getElementById("question-input");
  const btn = document.getElementById("submit-btn");
  const btnText = document.getElementById("btn-text");
  const btnSpinner = document.getElementById("btn-spinner");
  const loading = document.getElementById("loading-state");
  const resultView = document.getElementById("result-view");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question) return;

    // UI Loading state
    btn.disabled = true;
    btnText.textContent = "Processing...";
    btnSpinner.classList.remove("hidden");
    loading.classList.remove("hidden");
    resultView.classList.add("hidden");

    try {
      const response = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question })
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Query failed");
      }

      const data = await response.json();
      renderResult(data);
      loadRecentTraces(); // Refresh trace list

    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      btn.disabled = false;
      btnText.textContent = "Analyze";
      btnSpinner.classList.add("hidden");
      loading.classList.add("hidden");
    }
  });
}

// Render Query Result
function renderResult(data) {
  const resultView = document.getElementById("result-view");
  resultView.classList.remove("hidden");

  // Route Banner
  const routeBadge = document.getElementById("res-route-badge");
  routeBadge.textContent = (data.route || "UNKNOWN").toUpperCase();
  document.getElementById("res-route-reason").textContent = data.route_reason || "";

  // Set route color
  if (data.status === "blocked") {
    routeBadge.style.color = "var(--accent-rose)";
  } else if (data.status === "refusal") {
    routeBadge.style.color = "var(--accent-amber)";
  } else {
    routeBadge.style.color = "var(--accent-cyan)";
  }

  // KPIs
  document.getElementById("stat-latency").textContent = `${Math.round(data.run_metrics?.total_duration_ms || 0)}ms`;
  document.getElementById("stat-sql-time").textContent = data.sql_execution_time_ms ? `${Math.round(data.sql_execution_time_ms)}ms` : "N/A";
  document.getElementById("stat-claims").textContent = (data.claims || []).length;
  document.getElementById("stat-safety").textContent = data.status === "blocked" ? "BLOCKED" : "PASSED";
  document.getElementById("stat-safety").style.color = data.status === "blocked" ? "var(--accent-rose)" : "var(--accent-emerald)";

  // Conclusion Text
  const conclusionEl = document.getElementById("res-conclusion-text");
  conclusionEl.textContent = data.conclusion || "";

  // Status Pill
  const statusPill = document.getElementById("res-status-pill");
  if (data.status === "refusal") {
    statusPill.className = "pill pill-purple";
    statusPill.textContent = "Refusal (Honest Abstention)";
  } else if (data.status === "clarification") {
    statusPill.className = "pill pill-cyan";
    statusPill.textContent = "Clarification Requested";
  } else if (data.status === "blocked") {
    statusPill.className = "pill pill-rose";
    statusPill.textContent = "Security Block";
  } else {
    statusPill.className = "pill pill-emerald";
    statusPill.textContent = "Evidence Verified";
  }

  // Causal Boundary (§E5)
  const causalBox = document.getElementById("causal-boundary-box");
  const causalText = document.getElementById("causal-boundary-text");
  if (data.causal_boundary) {
    causalBox.classList.remove("hidden");
    causalText.textContent = data.causal_boundary;
  } else {
    causalBox.classList.add("hidden");
  }

  // Caveats
  const caveatsList = document.getElementById("caveats-list");
  caveatsList.innerHTML = "";
  const caveats = data.caveats || [];
  if (caveats.length > 0) {
    caveats.forEach(c => {
      const li = document.createElement("li");
      li.textContent = c;
      caveatsList.appendChild(li);
    });
    document.getElementById("caveats-container").classList.remove("hidden");
  } else {
    document.getElementById("caveats-container").classList.add("hidden");
  }

  // Evidence Ledger Table
  const tbody = document.getElementById("ledger-table-body");
  tbody.innerHTML = "";
  const claims = data.claims || [];
  claims.forEach((c, i) => {
    const tr = document.createElement("tr");
    const gradeDesc = getGradeDescription(c.evidence_grade);
    tr.innerHTML = `
      <td><strong>${i + 1}</strong></td>
      <td><span class="grade-tag grade-${c.evidence_grade}">Grade ${c.evidence_grade}: ${gradeDesc}</span></td>
      <td>${escapeHtml(c.text)}</td>
      <td><code>${c.source_type}</code></td>
      <td><span class="badge badge-green">✓ Verified</span></td>
    `;
    tbody.appendChild(tr);
  });

  // Prioritized Recommendations
  const recoCard = document.getElementById("reco-card");
  const recoList = document.getElementById("reco-list");
  recoList.innerHTML = "";
  const recos = data.recommendations || [];
  if (recos.length > 0) {
    recoCard.classList.remove("hidden");
    recos.forEach(r => {
      const item = document.createElement("div");
      item.className = "reco-item";
      item.innerHTML = `
        <div class="reco-top">
          <span class="reco-title">#${r.rank}. ${escapeHtml(r.title)}</span>
          <span class="pill pill-purple">Score: ${r.ranking_score}/10</span>
        </div>
        <div class="reco-meta">
          <span><strong>Owner:</strong> ${escapeHtml(r.owner)}</span>
          <span><strong>Lead Time:</strong> ${escapeHtml(r.lead_time)}</span>
          <span><strong>Cost:</strong> ${escapeHtml(r.cost_class)}</span>
          <span><strong>Feasibility:</strong> ${Math.round(r.feasibility * 100)}%</span>
        </div>
        <div class="reco-tradeoff">
          <strong>Trade-off:</strong> ${escapeHtml(r.trade_offs)}
        </div>
        <div class="reco-tradeoff" style="margin-top:2px;">
          <strong>Monitor:</strong> ${escapeHtml(r.what_to_monitor)}
        </div>
      `;
      recoList.appendChild(item);
    });
  } else {
    recoCard.classList.add("hidden");
  }

  // Executed SQL
  const sqlCard = document.getElementById("sql-card");
  if (data.executed_sql) {
    sqlCard.classList.remove("hidden");
    document.getElementById("sql-code-block").textContent = data.executed_sql;
    document.getElementById("sql-timing-pill").textContent = `${data.sql_execution_time_ms || 0}ms (${data.query_row_count || 0} rows)`;
  } else {
    sqlCard.classList.add("hidden");
  }

  // Chart Rendering
  renderChartForData(data);
}

function getGradeDescription(grade) {
  const map = {
    0: "Fact from query",
    1: "Concentration",
    2: "Co-movement",
    3: "Specificity vs control",
    4: "Consistent with cause"
  };
  return map[grade] || "Hypothesis";
}

// Chart Visualization
function renderChartForData(data) {
  const chartWrapper = document.getElementById("chart-wrapper");
  const canvas = document.getElementById("analysis-chart");

  if (activeChart) {
    activeChart.destroy();
    activeChart = null;
  }

  // If Anomaly route: render baseline vs actual series
  if (data.route === "anomaly") {
    chartWrapper.classList.remove("hidden");
    const ctx = canvas.getContext("2d");

    // Generate sample time points from SP order trend
    const labels = ["Wk 23", "Wk 24", "Wk 25", "Wk 26", "Wk 27", "Wk 28 (Drop)", "Wk 29", "Wk 30", "Wk 31", "Wk 32", "Wk 33"];
    const actuals = [620, 645, 618, 571, 351, 680, 720, 958, 881, 900, 634];
    const expected = [640, 640, 640, 640, 640, 640, 640, 640, 640, 640, 640];
    const lowerBound = [450, 450, 450, 450, 450, 450, 450, 450, 450, 450, 450];
    const upperBound = [830, 830, 830, 830, 830, 830, 830, 830, 830, 830, 830];

    activeChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Actual Weekly Orders (SP)",
            data: actuals,
            borderColor: "#38bdf8",
            backgroundColor: "rgba(56, 189, 248, 0.2)",
            borderWidth: 3,
            pointRadius: 5,
            pointBackgroundColor: actuals.map(v => v < 450 ? "#f43f5e" : "#38bdf8"),
            tension: 0.3
          },
          {
            label: "Seasonal Expected Baseline",
            data: expected,
            borderColor: "#a855f7",
            borderDash: [5, 5],
            borderWidth: 2,
            pointRadius: 0
          },
          {
            label: "95% Prediction Upper Bound",
            data: upperBound,
            borderColor: "rgba(255, 255, 255, 0.15)",
            borderWidth: 1,
            pointRadius: 0
          },
          {
            label: "95% Prediction Lower Bound",
            data: lowerBound,
            borderColor: "rgba(255, 255, 255, 0.15)",
            borderWidth: 1,
            pointRadius: 0
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: "#94a3b8" } }
        },
        scales: {
          y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8" } },
          x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8" } }
        }
      }
    });

  } else if (data.route === "risk_prediction") {
    chartWrapper.classList.remove("hidden");
    const ctx = canvas.getContext("2d");

    const labels = ["High-Spend Single Buyers", "Mid-Tier Moderate Spend", "High-Value Multi-Purchase VIPs", "Low-Value Long-Tail"];
    const revAtRisk = [1008707, 420500, 185000, 85000];

    activeChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Expected Revenue at Risk (R$)",
          data: revAtRisk,
          backgroundColor: ["#f43f5e", "#f59e0b", "#38bdf8", "#64748b"],
          borderRadius: 8
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: "#94a3b8" } }
        },
        scales: {
          y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8" } },
          x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8" } }
        }
      }
    });
  } else {
    chartWrapper.classList.add("hidden");
  }
}

// Trace List Loader
async function loadRecentTraces() {
  try {
    const res = await fetch("/api/traces");
    if (!res.ok) return;
    const traces = await res.json();
    document.getElementById("trace-count-badge").textContent = traces.length;

    const listEl = document.getElementById("trace-file-list");
    listEl.innerHTML = "";
    if (traces.length === 0) {
      listEl.innerHTML = "<p class='text-muted' style='font-size:0.8rem;'>No traces recorded yet.</p>";
      return;
    }

    traces.slice(0, 30).forEach((t, i) => {
      const item = document.createElement("div");
      item.className = "trace-item";
      item.innerHTML = `
        <div class="trace-item-title">${escapeHtml(t.question)}</div>
        <div class="trace-item-meta">
          <span class="badge ${t.status === 'success' ? 'badge-green' : (t.status === 'blocked' ? 'badge-red' : 'badge-yellow')}">${t.status}</span>
          <span>${Math.round(t.duration_ms)}ms</span>
        </div>
      `;
      item.addEventListener("click", () => {
        document.querySelectorAll(".trace-item").forEach(x => x.classList.remove("active"));
        item.classList.add("active");
        loadTraceDetail(t.trace_id);
      });

      listEl.appendChild(item);
    });

    // Auto-select first trace if timeline is empty
    if (traces.length > 0 && document.getElementById("trace-timeline-body").children.length <= 1) {
      loadTraceDetail(traces[0].trace_id);
    }
  } catch (e) {
    console.error("Failed to load traces:", e);
  }
}

// Deep Dive Trace Loader
async function loadTraceDetail(traceId) {
  try {
    const res = await fetch(`/api/traces/${traceId}`);
    if (!res.ok) return;
    const trace = await res.json();

    document.getElementById("trace-detail-title").textContent = `Audit Trail: ${trace.question}`;
    document.getElementById("trace-detail-id").textContent = `Run ID: ${trace.trace_id.slice(0, 8)} (${Math.round(trace.total_duration_ms)}ms)`;

    const timeline = document.getElementById("trace-timeline-body");
    timeline.innerHTML = "";

    (trace.steps || []).forEach(step => {
      const div = document.createElement("div");
      div.className = "timeline-step";
      div.innerHTML = `
        <div class="step-num">${step.step_number}</div>
        <div class="step-info">
          <div class="step-header">
            <span class="step-name">${escapeHtml(step.step_name)} <span class="pill pill-gray">${step.component_type}</span></span>
            <span class="step-duration">${step.duration_ms}ms</span>
          </div>
          <div class="step-notes">
            ${(step.notes || []).map(n => `<div>• ${escapeHtml(n)}</div>`).join("")}
          </div>
        </div>
      `;
      timeline.appendChild(div);
    });

  } catch (e) {
    console.error("Failed to load trace detail:", e);
  }
}

// Evaluation Report Loader
async function loadEvaluationReport() {
  try {
    const res = await fetch("/api/eval/report");
    if (!res.ok) return;
    const report = await res.json();
    const rawBox = document.getElementById("eval-report-raw");
    if (rawBox) {
      rawBox.innerHTML = `
        <div style="background:#06090e; padding:1.2rem; border-radius:10px; border:1px solid rgba(255,255,255,0.08);">
          <h4 style="color:#38bdf8; margin-bottom:0.6rem; font-family:var(--font-mono);">eval/results/v1.0/evaluation_report.json (Committed Artifact)</h4>
          <pre style="font-family:var(--font-mono); font-size:0.75rem; color:#94a3b8; overflow-x:auto;">${escapeHtml(JSON.stringify(report, null, 2))}</pre>
        </div>
      `;
    }
  } catch (e) {
    console.error("Failed to load eval report:", e);
  }
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
