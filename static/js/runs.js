/**
 * runs.js — Runs tab: history table + "Run Now" button + polling status modal.
 */

let _pollTimer      = null;
let _pollingRunId   = null;

window.loadTab_runs = async function loadTab_runs() {
  // Wire up the Run Now button once
  const runBtn = document.getElementById("run-now-btn");
  if (runBtn && !runBtn._wired) {
    runBtn._wired = true;
    runBtn.addEventListener("click", handleRunNow);
  }

  await fetchAndRenderRuns();
};

/* --------------------------------------------------------------------------
   Run history table
   -------------------------------------------------------------------------- */

async function fetchAndRenderRuns() {
  const tbody = document.getElementById("runs-tbody");
  tbody.innerHTML = `<tr><td colspan="6"><div class="loader">Loading runs…</div></td></tr>`;

  let runs = null;
  try {
    runs = await window.apiFetch("/api/runs?limit=20");
  } catch (err) {
    console.error("Runs fetch error:", err);
    tbody.innerHTML = `<tr><td colspan="6" style="color:var(--muted);padding:1.5rem;text-align:center;">Failed to load runs.</td></tr>`;
    return;
  }

  if (!runs || runs.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6">
          <div class="empty-state">
            <div class="empty-icon">📭</div>
            <p>No pipeline runs yet — click "Run Now" to start the first collection.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = "";
  runs.forEach((run) => {
    tbody.appendChild(buildRunRow(run));
  });
}

function buildRunRow(run) {
  const tr = document.createElement("tr");

  // Run ID
  td(tr, `#${run.id}`, { mono: true, muted: true });

  // ISO week
  td(tr, run.iso_week ?? "—");

  // Status badge
  const statusTd = document.createElement("td");
  statusTd.appendChild(buildStatusBadge(run.status));
  tr.appendChild(statusTd);

  // Started at
  td(tr, window.fmtDatetime(run.started_at), { muted: true, small: true });

  // Duration
  td(tr, window.fmtDuration(run.started_at, run.completed_at), { muted: true });

  // Stage
  td(tr, run.stage ?? "—", { muted: true, small: true });

  return tr;
}

function td(tr, text, opts = {}) {
  const cell = document.createElement("td");
  if (opts.muted)  cell.style.color    = "var(--muted)";
  if (opts.small)  cell.style.fontSize = "0.8rem";
  if (opts.mono)   cell.style.fontFamily = "monospace";
  cell.textContent = text;
  tr.appendChild(cell);
  return cell;
}

function buildStatusBadge(status) {
  const span = document.createElement("span");
  const s    = (status ?? "unknown").toLowerCase();
  span.className   = `status-badge ${s}`;
  span.textContent = s;
  return span;
}

/* --------------------------------------------------------------------------
   Run Now flow
   -------------------------------------------------------------------------- */

async function handleRunNow() {
  const btn = document.getElementById("run-now-btn");
  btn.disabled    = true;
  btn.textContent = "Starting…";

  let result = null;
  try {
    const res = await fetch("/api/run/trigger", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ track: "all" }),
    });

    if (res.status === 409) {
      const body = await res.json();
      alert(`A run for this week already exists (run #${body.run_id}, status: ${body.status}).`);
      btn.disabled    = false;
      btn.textContent = "Run Now";
      return;
    }

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Trigger failed: ${res.status} — ${body}`);
    }

    result = await res.json();
  } catch (err) {
    console.error("Run trigger error:", err);
    alert(`Could not start a run: ${err.message}`);
    btn.disabled    = false;
    btn.textContent = "Run Now";
    return;
  }

  btn.disabled    = false;
  btn.textContent = "Run Now";

  openRunModal(result.run_id, result.iso_week);
  await fetchAndRenderRuns(); // Refresh table so the new run appears
}

/* --------------------------------------------------------------------------
   Status modal
   -------------------------------------------------------------------------- */

function openRunModal(runId, isoWeek) {
  _pollingRunId = runId;

  const overlay  = document.getElementById("run-modal");
  const metaEl   = document.getElementById("run-modal-meta");
  const closeBtn = document.getElementById("run-modal-close");

  metaEl.textContent     = `Run #${runId} · Week ${isoWeek ?? "—"}`;
  setProgress(0, "Queued");
  closeBtn.disabled      = true;

  overlay.classList.add("open");

  // Wire close button (one-time)
  closeBtn.onclick = () => closeRunModal();

  // Click outside to close only once complete
  overlay.onclick = (e) => {
    if (e.target === overlay && !closeBtn.disabled) closeRunModal();
  };

  // Start polling
  stopPolling();
  _pollTimer = setInterval(() => pollRunStatus(runId), 3000);
  pollRunStatus(runId); // Immediate first poll
}

function closeRunModal() {
  stopPolling();
  document.getElementById("run-modal").classList.remove("open");
  fetchAndRenderRuns(); // Refresh table after closing
}

function stopPolling() {
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

async function pollRunStatus(runId) {
  let statusData = null;
  try {
    statusData = await window.apiFetch(`/api/run/${runId}/status`);
  } catch (err) {
    console.error("Status poll error:", err);
    return;
  }

  if (!statusData) {
    stopPolling();
    setProgress(0, "Run not found");
    document.getElementById("run-modal-close").disabled = false;
    return;
  }

  const { status, stage, progress_pct } = statusData;
  const stageLabel = stage ? capitalize(stage) : capitalize(status ?? "Running");
  setProgress(progress_pct ?? 0, stageLabel);

  if (status === "completed" || status === "failed") {
    stopPolling();
    const closeBtn = document.getElementById("run-modal-close");
    closeBtn.disabled = false;

    const metaEl = document.getElementById("run-modal-meta");
    const suffix = status === "completed" ? " — Complete" : " — Failed";
    metaEl.textContent += suffix;

    await fetchAndRenderRuns(); // Update table while modal is still open
  }
}

function setProgress(pct, stageLabel) {
  const bar       = document.getElementById("run-progress-bar");
  const stageEl   = document.getElementById("run-stage-label");
  const pctEl     = document.getElementById("run-pct-label");

  bar.style.width        = `${Math.min(100, Math.max(0, pct))}%`;
  stageEl.textContent    = stageLabel;
  pctEl.textContent      = `${Math.round(pct)}%`;
}

function capitalize(str) {
  if (!str) return str;
  return str.charAt(0).toUpperCase() + str.slice(1);
}
