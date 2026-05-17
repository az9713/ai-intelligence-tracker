/**
 * adoption.js — Adoption tab: factor heatmap table + industry detail panel.
 */

let _adoptionMomentumChart = null;
let _adoptionRadarChart    = null;
let _selectedIndustry      = null;
let _adoptionScores        = [];

window.loadTab_adoption = async function loadTab_adoption() {
  const heatmapWrap = document.getElementById("adoption-heatmap-wrap");
  const detailPanel = document.getElementById("adoption-industry-detail");

  window.renderLoader(heatmapWrap);
  detailPanel.style.display = "none";

  // Destroy stale charts
  if (_adoptionMomentumChart) { _adoptionMomentumChart.destroy(); _adoptionMomentumChart = null; }
  if (_adoptionRadarChart)    { _adoptionRadarChart.destroy();    _adoptionRadarChart    = null; }

  let data = null;
  try {
    data = await window.apiFetch("/api/adoption/latest");
  } catch (err) {
    console.error("Adoption fetch error:", err);
    window.renderEmpty(heatmapWrap, "Failed to load adoption data.");
    return;
  }

  if (!data || !data.scores || data.scores.length === 0) {
    window.renderEmpty(heatmapWrap, "No adoption data yet — run the collection.");
    return;
  }

  _adoptionScores   = data.scores;
  _selectedIndustry = null;

  renderHeatmap(heatmapWrap, data.scores);
};

/* --------------------------------------------------------------------------
   Heatmap table
   -------------------------------------------------------------------------- */

const FACTORS = window.FACTOR_KEYS;

function renderHeatmap(container, scores) {
  const factorHeaders = FACTORS.map((f) =>
    `<th title="${window.escapeHtml(window.FACTOR_LABELS[f] ?? f)}">${window.escapeHtml(shortFactorLabel(f))}</th>`
  ).join("");

  const rows = scores.map((s) => {
    const industryLabel = window.INDUSTRY_LABELS[s.industry] ?? s.industry;
    const momentumColor = window.scoreColor(s.momentum_score);
    const deltaInfo     = window.formatDelta(s.score_delta);

    const factorCells = FACTORS.map((f) => {
      const val   = s[f] ?? 3;
      const color = window.scoreColor(val);
      return `
        <td title="${window.escapeHtml(window.FACTOR_LABELS[f] ?? f)}: ${val}">
          <span class="heat-cell" style="background:${color}; opacity:0.85;">${val}</span>
        </td>
      `;
    }).join("");

    return `
      <tr data-industry="${window.escapeHtml(s.industry)}">
        <td>
          <span style="font-weight:600;">${window.escapeHtml(industryLabel)}</span>
          <span class="delta ${deltaInfo.className}" style="margin-left:0.4rem;font-size:0.75rem;">${window.escapeHtml(deltaInfo.text)}</span>
        </td>
        ${factorCells}
        <td>
          <span class="heat-cell" style="background:${momentumColor}; font-size:0.85rem; width:32px; height:28px; font-weight:700;">${s.momentum_score}</span>
        </td>
      </tr>
    `;
  });

  container.innerHTML = `
    <table class="heatmap-table">
      <thead>
        <tr>
          <th>Industry</th>
          ${factorHeaders}
          <th>Momentum</th>
        </tr>
      </thead>
      <tbody>${rows.join("")}</tbody>
    </table>
  `;

  // Wire up row click to show industry detail
  container.querySelectorAll("tr[data-industry]").forEach((row) => {
    row.addEventListener("click", async () => {
      const industry = row.dataset.industry;

      // Toggle off if same industry clicked twice
      if (_selectedIndustry === industry) {
        _selectedIndustry = null;
        row.classList.remove("selected");
        document.getElementById("adoption-industry-detail").style.display = "none";
        return;
      }

      // Deselect previous
      container.querySelectorAll("tr.selected").forEach((r) => r.classList.remove("selected"));
      row.classList.add("selected");

      _selectedIndustry = industry;
      await showIndustryDetail(industry);
    });
  });
}

function shortFactorLabel(key) {
  const short = {
    labor_cost:               "Labor",
    workflow_repetitiveness:  "Workflow",
    digital_artifact:         "Digital",
    error_cost:               "Error",
    regulatory_burden:        "Regulatory",
    verification_feasibility: "Verify",
    tool_api_access:          "Tool API",
  };
  return short[key] ?? key;
}

/* --------------------------------------------------------------------------
   Industry detail panel
   -------------------------------------------------------------------------- */

async function showIndustryDetail(industry) {
  const panel = document.getElementById("adoption-industry-detail");
  panel.style.display = "block";

  const industryLabel = window.INDUSTRY_LABELS[industry] ?? industry;
  const scoreRow      = _adoptionScores.find((s) => s.industry === industry);

  panel.innerHTML = `
    <h2>${window.escapeHtml(industryLabel)} Detail</h2>
    <div class="loader">Loading history…</div>
    <div class="industry-rationale">
      ${scoreRow?.rationale ? window.escapeHtml(scoreRow.rationale) : ""}
    </div>
    <div class="industry-detail-grid">
      <div class="chart-card">
        <h3>12-Week Momentum</h3>
        <div class="chart-wrapper" style="height:240px;">
          <canvas id="adoption-momentum-chart"></canvas>
        </div>
      </div>
      <div class="chart-card">
        <h3>Factor Radar</h3>
        <div class="chart-wrapper" style="height:240px;">
          <canvas id="adoption-radar-chart"></canvas>
        </div>
      </div>
    </div>
  `;

  // Render factor radar immediately from existing data
  if (scoreRow) {
    renderFactorRadar(scoreRow);
  }

  // Fetch and render momentum history
  let histData = null;
  try {
    histData = await window.apiFetch(
      `/api/adoption/history?industry=${encodeURIComponent(industry)}&weeks=12`
    );
  } catch (err) {
    console.error("Adoption history fetch error:", err);
  }

  // Remove loader
  const loaderEl = panel.querySelector(".loader");
  if (loaderEl) loaderEl.remove();

  renderMomentumChart(histData, industry);

  // Scroll the panel into view
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderMomentumChart(histData, industry) {
  const canvas = document.getElementById("adoption-momentum-chart");
  if (!canvas) return;

  if (_adoptionMomentumChart) {
    _adoptionMomentumChart.destroy();
    _adoptionMomentumChart = null;
  }

  const history = histData?.history ?? [];

  if (!history.length) {
    canvas.parentElement.innerHTML = `
      <div class="empty-state" style="padding:1.5rem;">
        <p>No momentum history available.</p>
      </div>
    `;
    return;
  }

  const lastScore = history[history.length - 1]?.score ?? 3;
  const color     = window.scoreColor(lastScore);

  _adoptionMomentumChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: history.map((h) => h.iso_week),
      datasets: [{
        label: "Momentum Score",
        data: history.map((h) => h.score),
        borderColor: color,
        backgroundColor: `${color}22`,
        borderWidth: 2.5,
        pointRadius: 4,
        pointBackgroundColor: color,
        tension: 0.3,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          min: 1,
          max: 5,
          ticks: { stepSize: 1, color: "#64748b", font: { size: 11 } },
          grid: { color: "rgba(255,255,255,0.06)" },
        },
        x: {
          ticks: { color: "#64748b", font: { size: 11 }, maxRotation: 45 },
          grid: { display: false },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` Momentum: ${ctx.parsed.y}`,
          },
        },
      },
    },
  });
}

function renderFactorRadar(scoreRow) {
  const canvas = document.getElementById("adoption-radar-chart");
  if (!canvas) return;

  if (_adoptionRadarChart) {
    _adoptionRadarChart.destroy();
    _adoptionRadarChart = null;
  }

  const labels = FACTORS.map((f) => window.FACTOR_LABELS[f] ?? f);
  const values = FACTORS.map((f) => scoreRow[f] ?? 3);

  _adoptionRadarChart = new Chart(canvas, {
    type: "radar",
    data: {
      labels,
      datasets: [{
        label: "Factor Scores",
        data: values,
        backgroundColor: "rgba(79,142,247,0.2)",
        borderColor: "#4f8ef7",
        borderWidth: 2,
        pointBackgroundColor: values.map((v) => window.scoreColor(v)),
        pointRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        r: {
          min: 0,
          max: 5,
          ticks: {
            stepSize: 1,
            color: "#64748b",
            backdropColor: "transparent",
            font: { size: 9 },
          },
          grid: { color: "rgba(255,255,255,0.07)" },
          angleLines: { color: "rgba(255,255,255,0.07)" },
          pointLabels: {
            color: "#94a3b8",
            font: { size: 9 },
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.parsed.r}`,
          },
        },
      },
    },
  });
}
