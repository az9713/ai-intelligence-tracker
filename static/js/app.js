/**
 * app.js — Core router and shared utilities for the AI Intelligence Dashboard.
 *
 * Loaded before all tab files. Exposes helpers on window so tab modules can
 * import them without a bundler.
 */

/* ==========================================================================
   Label maps (mirrors config.py — kept in sync manually)
   ========================================================================== */

window.LAYER_LABELS = {
  gpu:         "GPU / Accelerators",
  hbm:         "HBM Memory",
  networking:  "Rack Networking",
  dc_shell:    "Data-Center Shell",
  power:       "Power / Grid",
  cooling:     "Cooling",
  fab:         "Fab Capacity",
};

window.INDUSTRY_LABELS = {
  software_eng:     "Software Engineering",
  legal:            "Legal",
  accounting:       "Accounting",
  insurance:        "Insurance",
  healthcare_admin: "Healthcare Admin",
  finance_ops:      "Finance Ops",
  marketing:        "Marketing",
  customer_support: "Customer Support",
  manufacturing:    "Manufacturing",
  defense_aero:     "Defense / Aerospace",
};

window.FACTOR_LABELS = {
  labor_cost:               "Labor Cost",
  workflow_repetitiveness:  "Workflow Repetitiveness",
  digital_artifact:         "Digital Artifact",
  error_cost:               "Error Cost",
  regulatory_burden:        "Regulatory Burden",
  verification_feasibility: "Verification Feasibility",
  tool_api_access:          "Tool / API Access",
};

window.FACTOR_KEYS = [
  "labor_cost",
  "workflow_repetitiveness",
  "digital_artifact",
  "error_cost",
  "regulatory_burden",
  "verification_feasibility",
  "tool_api_access",
];

/* ==========================================================================
   Shared utilities
   ========================================================================== */

/**
 * Fetch a JSON endpoint. Returns parsed data on success.
 * Returns null (and does NOT throw) on 404 — callers treat null as "no data".
 * Throws on other HTTP errors or network failures.
 *
 * @param {string} path  — e.g. "/api/bottleneck/latest"
 * @returns {Promise<any|null>}
 */
window.apiFetch = async function apiFetch(path) {
  const res = await fetch(path);
  if (res.status === 404) return null;
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status} for ${path}: ${body}`);
  }
  return res.json();
};

/**
 * Map a score (1–5) to its CSS colour string.
 * @param {number} score
 * @returns {string}
 */
window.scoreColor = function scoreColor(score) {
  const map = {
    1: "#22c55e",
    2: "#84cc16",
    3: "#eab308",
    4: "#f97316",
    5: "#ef4444",
  };
  return map[Math.round(score)] ?? "#64748b";
};

/**
 * Return a delta symbol and CSS class for display.
 * Convention: positive delta = score went up = worse = shown red (▲).
 *             negative delta = score went down = better = shown green (▼).
 *
 * @param {number|null} delta
 * @returns {{ symbol: string, className: string, text: string }}
 */
window.formatDelta = function formatDelta(delta) {
  if (delta === null || delta === undefined) {
    return { symbol: "—", className: "none", text: "—" };
  }
  if (delta > 0) {
    return { symbol: "▲", className: "up", text: `▲ ${Math.abs(delta).toFixed(1)}` };
  }
  if (delta < 0) {
    return { symbol: "▼", className: "down", text: `▼ ${Math.abs(delta).toFixed(1)}` };
  }
  return { symbol: "—", className: "none", text: "—" };
};

/**
 * Escape HTML special characters to prevent XSS when injecting user-provided
 * text via innerHTML.
 * @param {string} str
 * @returns {string}
 */
window.escapeHtml = function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
};

/**
 * Format an ISO datetime string into a short local representation.
 * @param {string|null} isoStr
 * @returns {string}
 */
window.fmtDatetime = function fmtDatetime(isoStr) {
  if (!isoStr) return "—";
  try {
    return new Date(isoStr).toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return isoStr;
  }
};

/**
 * Compute a human-readable duration between two ISO datetime strings.
 * @param {string|null} start
 * @param {string|null} end
 * @returns {string}
 */
window.fmtDuration = function fmtDuration(start, end) {
  if (!start || !end) return "—";
  const ms = new Date(end) - new Date(start);
  if (isNaN(ms) || ms < 0) return "—";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
};

/**
 * Render the "no data" empty state into a container element.
 * @param {HTMLElement} el
 * @param {string} [msg]
 */
window.renderEmpty = function renderEmpty(el, msg) {
  el.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">📭</div>
      <p>${window.escapeHtml(msg ?? "No data yet — run the collection to populate this view.")}</p>
    </div>
  `;
};

/**
 * Render a loading spinner into a container element.
 * @param {HTMLElement} el
 */
window.renderLoader = function renderLoader(el) {
  el.innerHTML = `<div class="loader">Loading…</div>`;
};

/* ==========================================================================
   Hash-based router
   ========================================================================== */

const VALID_TABS = ["overview", "bottleneck", "adoption", "memos", "signals", "runs"];
const DEFAULT_TAB = "overview";

function getTabFromHash() {
  const hash = location.hash.replace("#", "").trim();
  return VALID_TABS.includes(hash) ? hash : DEFAULT_TAB;
}

function activateTab(tabName) {
  // Hide all tab panels
  document.querySelectorAll(".tab-content").forEach((el) => {
    el.classList.remove("active");
  });

  // Deactivate all nav buttons
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.remove("active");
    btn.setAttribute("aria-selected", "false");
  });

  // Show the target panel
  const panel = document.getElementById(`tab-${tabName}`);
  if (panel) {
    panel.classList.add("active");
  }

  // Activate the matching nav button
  const btn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
  if (btn) {
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");
  }

  // Call the tab's load function if registered
  const loader = window[`loadTab_${tabName}`];
  if (typeof loader === "function") {
    loader();
  }
}

// Wire up nav buttons to update the hash
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      if (location.hash !== `#${tab}`) {
        location.hash = tab;
      } else {
        // Same tab — re-run loader to refresh
        activateTab(tab);
      }
    });
  });

  // Initial activation
  activateTab(getTabFromHash());

  // Load health info into header
  loadHealth();
});

// React to hash changes
window.addEventListener("hashchange", () => {
  activateTab(getTabFromHash());
});

/* ==========================================================================
   Header — last updated timestamp from /api/health
   ========================================================================== */

async function loadHealth() {
  const el = document.getElementById("last-updated");
  try {
    const data = await window.apiFetch("/api/health");
    if (!data) {
      el.textContent = "No data available";
      return;
    }
    const status = data.status === "ok" ? "OK" : data.status;
    const week   = data.iso_week ? ` · Week ${data.iso_week}` : "";
    const runAt  = data.last_run_date ? ` · Last run: ${data.last_run_date}` : "";
    el.textContent = `System ${status}${week}${runAt}`;
  } catch (err) {
    console.error("Health check failed:", err);
    el.textContent = "Status unknown";
  }
}
