/**
 * bottleneck.js — Bottleneck tab: layer cards grid + history line chart.
 */

let _bottleneckHistoryChart = null;
let _selectedLayer = null;
let _latestScores  = [];

window.loadTab_bottleneck = async function loadTab_bottleneck() {
  const gridEl    = document.getElementById("bottleneck-layer-grid");
  const selectorEl = document.getElementById("bottleneck-layer-selector");

  window.renderLoader(gridEl);
  selectorEl.innerHTML = "";

  let data = null;
  try {
    data = await window.apiFetch("/api/bottleneck/latest");
  } catch (err) {
    console.error("Bottleneck fetch error:", err);
    window.renderEmpty(gridEl, "Failed to load bottleneck data.");
    return;
  }

  if (!data || !data.scores || data.scores.length === 0) {
    window.renderEmpty(gridEl, "No bottleneck data yet — run the collection.");
    return;
  }

  _latestScores = data.scores;

  // Render layer cards
  renderLayerCards(gridEl, data.scores);

  // Render layer selector chips for history chart
  renderLayerSelector(selectorEl, data.scores);

  // Default: load history for first layer in list
  const firstLayer = data.scores[0]?.layer;
  if (firstLayer) {
    _selectedLayer = firstLayer;
    await loadLayerHistory(firstLayer);
    highlightChip(firstLayer);
  }
};

/* --------------------------------------------------------------------------
   Layer cards grid
   -------------------------------------------------------------------------- */

function renderLayerCards(container, scores) {
  if (!scores.length) {
    window.renderEmpty(container);
    return;
  }

  container.innerHTML = scores.map((s) => layerCardHtml(s)).join("");

  // Wire up evidence buttons and rationale expand
  container.querySelectorAll(".evidence-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const panel = btn.closest(".layer-card").querySelector(".evidence-panel");
      const isOpen = panel.classList.contains("open");
      panel.classList.toggle("open", !isOpen);
      btn.textContent = isOpen ? "Evidence" : "Hide Evidence";
    });
  });

  container.querySelectorAll(".rationale-more").forEach((moreBtn) => {
    moreBtn.addEventListener("click", () => {
      const card = moreBtn.closest(".layer-card");
      const fullEl  = card.querySelector(".rationale-full");
      const shortEl = card.querySelector(".rationale-short");
      const isShowing = fullEl.style.display !== "none";
      fullEl.style.display  = isShowing ? "none"   : "inline";
      shortEl.style.display = isShowing ? "inline" : "none";
      moreBtn.textContent   = isShowing ? "Show more" : "Show less";
    });
  });
}

function layerCardHtml(s) {
  const label      = window.LAYER_LABELS[s.layer] ?? s.layer;
  const color      = window.scoreColor(s.score);
  const deltaInfo  = window.formatDelta(s.score_delta);
  const confPct    = Math.round((s.confidence ?? 0) * 100);

  const rationale  = s.rationale ?? "";
  const truncated  = rationale.length > 120 ? rationale.slice(0, 120) + "…" : rationale;
  const needsMore  = rationale.length > 120;

  const indicators = (s.leading_indicators ?? [])
    .map((ind) => `<li>${window.escapeHtml(ind)}</li>`)
    .join("");

  const urls = (s.evidence_urls ?? [])
    .map((url) => `<li><a href="${window.escapeHtml(url)}" target="_blank" rel="noopener">${window.escapeHtml(url)}</a></li>`)
    .join("");

  return `
    <div class="layer-card">
      <div class="layer-card-header">
        <div class="layer-card-title">${window.escapeHtml(label)}</div>
        <div class="score-badge" style="background:${color}; color:#000;">${s.score}</div>
        <span class="delta ${deltaInfo.className}">${window.escapeHtml(deltaInfo.text)}</span>
      </div>

      <div class="layer-card-meta">
        <span>Confidence</span>
        <span>${confPct}%</span>
      </div>
      <div class="conf-bar-wrap">
        <div class="conf-bar-fill" style="width:${confPct}%; background:${color};"></div>
      </div>

      <div class="layer-card-rationale" style="margin-top:0.6rem;">
        <span class="rationale-short">${window.escapeHtml(truncated)}</span>
        <span class="rationale-full" style="display:none;">${window.escapeHtml(rationale)}</span>
        ${needsMore
          ? `<button class="rationale-more">Show more</button>`
          : ""}
      </div>

      <button class="evidence-btn">Evidence</button>

      <div class="evidence-panel">
        ${indicators
          ? `<strong style="font-size:0.78rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.04em;">Leading Indicators</strong>
             <ul>${indicators}</ul>`
          : ""}
        ${urls
          ? `<strong style="font-size:0.78rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.04em;">Evidence URLs</strong>
             <ul>${urls}</ul>`
          : ""}
        ${!indicators && !urls
          ? `<p style="color:var(--muted);">No evidence recorded for this layer.</p>`
          : ""}
      </div>
    </div>
  `;
}

/* --------------------------------------------------------------------------
   Layer selector chips for history chart
   -------------------------------------------------------------------------- */

function renderLayerSelector(container, scores) {
  container.innerHTML = scores.map((s) => {
    const label = window.LAYER_LABELS[s.layer] ?? s.layer;
    return `<button class="layer-chip" data-layer="${window.escapeHtml(s.layer)}">${window.escapeHtml(label)}</button>`;
  }).join("");

  container.querySelectorAll(".layer-chip").forEach((chip) => {
    chip.addEventListener("click", async () => {
      const layer = chip.dataset.layer;
      if (layer === _selectedLayer) return;
      _selectedLayer = layer;
      highlightChip(layer);
      await loadLayerHistory(layer);
    });
  });
}

function highlightChip(layer) {
  document.querySelectorAll(".layer-chip").forEach((c) => {
    c.classList.toggle("active", c.dataset.layer === layer);
  });
}

/* --------------------------------------------------------------------------
   Layer history line chart
   -------------------------------------------------------------------------- */

async function loadLayerHistory(layer) {
  const canvas = document.getElementById("bottleneck-history-chart");
  if (!canvas) return;

  // Show a loading state in chart area
  if (_bottleneckHistoryChart) {
    _bottleneckHistoryChart.destroy();
    _bottleneckHistoryChart = null;
  }

  let histData = null;
  try {
    histData = await window.apiFetch(`/api/bottleneck/history?layer=${encodeURIComponent(layer)}&weeks=12`);
  } catch (err) {
    console.error("Bottleneck history fetch error:", err);
    return;
  }

  if (!histData || !histData.history || histData.history.length === 0) {
    canvas.parentElement.innerHTML = `
      <div class="empty-state" style="padding:2rem;">
        <p>No history data for ${window.escapeHtml(window.LAYER_LABELS[layer] ?? layer)} yet.</p>
      </div>
    `;
    return;
  }

  // Re-create canvas if it was replaced
  let chartCanvas = document.getElementById("bottleneck-history-chart");
  if (!chartCanvas) {
    chartCanvas = document.createElement("canvas");
    chartCanvas.id = "bottleneck-history-chart";
    document.querySelector(".chart-card .chart-wrapper").appendChild(chartCanvas);
  }

  const history = histData.history;
  const layerLabel = window.LAYER_LABELS[layer] ?? layer;
  const color      = window.scoreColor(
    history.length ? history[history.length - 1].score : 3
  );

  _bottleneckHistoryChart = new Chart(chartCanvas, {
    type: "line",
    data: {
      labels: history.map((h) => h.iso_week),
      datasets: [{
        label: layerLabel,
        data: history.map((h) => h.score),
        borderColor: color,
        backgroundColor: `${color}22`,
        borderWidth: 2.5,
        pointRadius: 4,
        pointHoverRadius: 6,
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
          reverse: false,
          ticks: {
            stepSize: 1,
            color: "#64748b",
            font: { size: 11 },
          },
          grid: { color: "rgba(255,255,255,0.06)" },
        },
        x: {
          ticks: {
            color: "#64748b",
            font: { size: 11 },
            maxRotation: 45,
          },
          grid: { display: false },
        },
      },
      plugins: {
        legend: {
          labels: { color: "#94a3b8", font: { size: 12 } },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` Score: ${ctx.parsed.y}`,
            afterLabel: (ctx) => {
              const pt = history[ctx.dataIndex];
              const d  = window.formatDelta(pt?.score_delta);
              return `Delta: ${d.text}`;
            },
          },
        },
      },
    },
  });
}
