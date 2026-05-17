/**
 * overview.js — Overview tab: KPI cards + bottleneck radar + adoption bar chart.
 */

/* Module-level chart handles so we can destroy before re-rendering. */
let _overviewRadarChart    = null;
let _overviewAdoptionChart = null;

window.loadTab_overview = async function loadTab_overview() {
  const kpiGrid = document.getElementById("overview-kpis");
  window.renderLoader(kpiGrid);

  // Reset chart area while loading
  destroyChart("_overviewRadarChart");
  destroyChart("_overviewAdoptionChart");

  let bData = null;
  let aData = null;

  try {
    [bData, aData] = await Promise.all([
      window.apiFetch("/api/bottleneck/latest"),
      window.apiFetch("/api/adoption/latest"),
    ]);
  } catch (err) {
    console.error("Overview fetch error:", err);
    window.renderEmpty(kpiGrid, "Failed to load data. Check the console for details.");
    return;
  }

  // Render KPIs
  renderOverviewKpis(kpiGrid, bData, aData);

  // Render charts
  renderBottleneckRadar(bData);
  renderAdoptionBar(aData);
};

/* --------------------------------------------------------------------------
   KPI cards
   -------------------------------------------------------------------------- */

function renderOverviewKpis(container, bData, aData) {
  const scores   = bData?.scores ?? [];
  const aScores  = aData?.scores ?? [];
  const isoWeek  = bData?.iso_week ?? aData?.iso_week ?? "—";

  // Average bottleneck score
  const avgScore = scores.length
    ? (scores.reduce((s, r) => s + r.score, 0) / scores.length).toFixed(1)
    : null;

  // Highest-risk layer (max score)
  const highestRisk = scores.length
    ? scores.reduce((a, b) => (b.score > a.score ? b : a))
    : null;

  // Top adoption mover (highest momentum_score)
  const topMover = aScores.length
    ? aScores.reduce((a, b) => (b.momentum_score > a.momentum_score ? b : a))
    : null;

  if (!scores.length && !aScores.length) {
    window.renderEmpty(container, "No data yet — run the collection to populate this view.");
    return;
  }

  const avgColor   = avgScore ? window.scoreColor(Math.round(parseFloat(avgScore))) : "#64748b";
  const riskColor  = highestRisk ? window.scoreColor(highestRisk.score) : "#64748b";
  const moverDelta = topMover ? window.formatDelta(topMover.score_delta) : null;

  container.innerHTML = `
    ${kpiCard(
      "Avg Bottleneck Score",
      avgScore !== null
        ? `<span style="color:${avgColor}">${avgScore}</span>`
        : "—",
      "mean of 7 layer scores (1=best, 5=worst)"
    )}
    ${kpiCard(
      "Highest-Risk Layer",
      highestRisk
        ? `<span style="font-size:1.1rem;font-weight:700;">${window.escapeHtml(window.LAYER_LABELS[highestRisk.layer] ?? highestRisk.layer)}</span>
           <span class="score-badge" style="background:${riskColor};margin-left:0.5rem;font-size:0.8rem;width:26px;height:26px;">${highestRisk.score}</span>`
        : "—",
      ""
    )}
    ${kpiCard(
      "Top Adoption Mover",
      topMover
        ? `<span style="font-size:1rem;font-weight:700;">${window.escapeHtml(window.INDUSTRY_LABELS[topMover.industry] ?? topMover.industry)}</span>
           <span class="delta ${moverDelta.className}" style="margin-left:0.5rem;">${window.escapeHtml(moverDelta.text)}</span>`
        : "—",
      topMover ? `Momentum score: ${topMover.momentum_score}` : ""
    )}
    ${kpiCard(
      "Current ISO Week",
      `<span style="font-size:1.5rem;font-weight:700;">${window.escapeHtml(isoWeek)}</span>`,
      "data collection period"
    )}
  `;
}

function kpiCard(label, valueHtml, sub) {
  return `
    <div class="kpi-card">
      <div class="kpi-label">${window.escapeHtml(label)}</div>
      <div class="kpi-value flex-center gap-sm" style="flex-wrap:wrap;min-height:2.5rem;">${valueHtml}</div>
      ${sub ? `<div class="kpi-sub">${window.escapeHtml(sub)}</div>` : ""}
    </div>
  `;
}

/* --------------------------------------------------------------------------
   Bottleneck radar chart
   -------------------------------------------------------------------------- */

function renderBottleneckRadar(bData) {
  const canvas = document.getElementById("overview-radar");
  if (!canvas) return;

  if (_overviewRadarChart) {
    _overviewRadarChart.destroy();
    _overviewRadarChart = null;
  }

  const scores = bData?.scores ?? [];

  if (!scores.length) {
    canvas.parentElement.innerHTML = `<div class="empty-state" style="padding:2rem;"><p>No bottleneck data.</p></div>`;
    return;
  }

  // Ensure we display in a deterministic layer order
  const layerOrder = Object.keys(window.LAYER_LABELS);
  const ordered = layerOrder
    .map((key) => scores.find((s) => s.layer === key))
    .filter(Boolean);

  const labels = ordered.map((s) => window.LAYER_LABELS[s.layer] ?? s.layer);
  const values = ordered.map((s) => s.score);

  _overviewRadarChart = new Chart(canvas, {
    type: "radar",
    data: {
      labels,
      datasets: [{
        label: "Bottleneck Score",
        data: values,
        backgroundColor: "rgba(79,142,247,0.25)",
        borderColor: "#4f8ef7",
        borderWidth: 2,
        pointBackgroundColor: values.map((v) => window.scoreColor(v)),
        pointRadius: 4,
        pointHoverRadius: 6,
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
            font: { size: 10 },
          },
          grid: { color: "rgba(255,255,255,0.07)" },
          angleLines: { color: "rgba(255,255,255,0.07)" },
          pointLabels: {
            color: "#94a3b8",
            font: { size: 11 },
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` Score: ${ctx.parsed.r}`,
          },
        },
      },
    },
  });
}

/* --------------------------------------------------------------------------
   Adoption horizontal bar chart
   -------------------------------------------------------------------------- */

function renderAdoptionBar(aData) {
  const canvas = document.getElementById("overview-adoption-bar");
  if (!canvas) return;

  if (_overviewAdoptionChart) {
    _overviewAdoptionChart.destroy();
    _overviewAdoptionChart = null;
  }

  const scores = aData?.scores ?? [];

  if (!scores.length) {
    canvas.parentElement.innerHTML = `<div class="empty-state" style="padding:2rem;"><p>No adoption data.</p></div>`;
    return;
  }

  // Sort descending by momentum_score
  const sorted = [...scores].sort((a, b) => b.momentum_score - a.momentum_score);

  const labels     = sorted.map((s) => window.INDUSTRY_LABELS[s.industry] ?? s.industry);
  const values     = sorted.map((s) => s.momentum_score);
  const barColors  = values.map((v) => window.scoreColor(v));

  _overviewAdoptionChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Momentum Score",
        data: values,
        backgroundColor: barColors,
        borderRadius: 4,
        borderSkipped: false,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          min: 0,
          max: 5,
          ticks: {
            color: "#64748b",
            stepSize: 1,
            font: { size: 11 },
          },
          grid: { color: "rgba(255,255,255,0.06)" },
        },
        y: {
          ticks: {
            color: "#94a3b8",
            font: { size: 11 },
          },
          grid: { display: false },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` Momentum: ${ctx.parsed.x}`,
          },
        },
        // Show value labels at end of bar via custom afterDatasetsDraw
      },
    },
    plugins: [{
      id: "barValueLabels",
      afterDatasetsDraw(chart) {
        const ctx2 = chart.ctx;
        chart.data.datasets.forEach((dataset, i) => {
          const meta = chart.getDatasetMeta(i);
          meta.data.forEach((bar, idx) => {
            const val = dataset.data[idx];
            const { x, y } = bar.tooltipPosition();
            ctx2.save();
            ctx2.fillStyle = "#e2e8f0";
            ctx2.font = "600 11px sans-serif";
            ctx2.textAlign = "left";
            ctx2.textBaseline = "middle";
            ctx2.fillText(val, x + 6, y);
            ctx2.restore();
          });
        });
      },
    }],
  });
}

/* Helper to safely destroy a chart stored in a module-level variable */
function destroyChart(varName) {
  // Access module scope variables directly
  if (varName === "_overviewRadarChart" && _overviewRadarChart) {
    _overviewRadarChart.destroy();
    _overviewRadarChart = null;
  }
  if (varName === "_overviewAdoptionChart" && _overviewAdoptionChart) {
    _overviewAdoptionChart.destroy();
    _overviewAdoptionChart = null;
  }
}
