/**
 * signals.js — Signals tab: filter bar + paginated table.
 */

const SIGNALS_PAGE_SIZE = 50;

let _signalsOffset       = 0;
let _signalsFilters      = {};
let _signalsExhausted    = false;
let _signalsInitialised  = false;

window.loadTab_signals = async function loadTab_signals() {
  if (!_signalsInitialised) {
    initSignalsToolbar();
    _signalsInitialised = true;
  }
  // Reset and re-fetch on every tab activation
  resetAndFetch();
};

/* --------------------------------------------------------------------------
   Toolbar
   -------------------------------------------------------------------------- */

function initSignalsToolbar() {
  const relSlider = document.getElementById("sig-relevance");
  const relVal    = document.getElementById("sig-rel-val");

  relSlider.addEventListener("input", () => {
    relVal.textContent = parseFloat(relSlider.value).toFixed(1);
  });

  document.getElementById("sig-apply-btn").addEventListener("click", () => {
    resetAndFetch();
  });

  // Allow Enter key in text inputs to apply
  ["sig-category", "sig-search"].forEach((id) => {
    document.getElementById(id).addEventListener("keydown", (e) => {
      if (e.key === "Enter") resetAndFetch();
    });
  });

  document.getElementById("signals-load-more-btn").addEventListener("click", () => {
    fetchAndAppendSignals();
  });
}

function readFilters() {
  return {
    track:        document.getElementById("sig-track").value.trim() || null,
    category:     document.getElementById("sig-category").value.trim() || null,
    min_relevance: parseFloat(document.getElementById("sig-relevance").value) || 0,
    search:       document.getElementById("sig-search").value.trim().toLowerCase() || null,
  };
}

function buildApiUrl(offset) {
  const f = _signalsFilters;
  const params = new URLSearchParams();
  if (f.track)                    params.set("track", f.track);
  if (f.category)                 params.set("category", f.category);
  if (f.min_relevance > 0)        params.set("min_relevance", f.min_relevance);
  params.set("limit",  SIGNALS_PAGE_SIZE);
  params.set("offset", offset);
  return `/api/signals?${params.toString()}`;
}

function resetAndFetch() {
  _signalsOffset    = 0;
  _signalsExhausted = false;
  _signalsFilters   = readFilters();

  const tbody    = document.getElementById("signals-tbody");
  const moreWrap = document.getElementById("signals-load-more-wrap");
  tbody.innerHTML = `<tr><td colspan="7"><div class="loader">Loading…</div></td></tr>`;
  moreWrap.style.display = "none";

  fetchAndAppendSignals(true);
}

/* --------------------------------------------------------------------------
   Fetch + render
   -------------------------------------------------------------------------- */

async function fetchAndAppendSignals(replace = false) {
  const moreBtn  = document.getElementById("signals-load-more-btn");
  const moreWrap = document.getElementById("signals-load-more-wrap");
  const tbody    = document.getElementById("signals-tbody");

  moreBtn.disabled   = true;
  moreBtn.textContent = "Loading…";

  let data = null;
  try {
    data = await window.apiFetch(buildApiUrl(_signalsOffset));
  } catch (err) {
    console.error("Signals fetch error:", err);
    if (replace) {
      tbody.innerHTML = `<tr><td colspan="7" style="color:var(--muted);padding:1.5rem;text-align:center;">Failed to load signals.</td></tr>`;
    }
    moreBtn.disabled    = false;
    moreBtn.textContent = "Load more";
    return;
  }

  const signals = data?.signals ?? [];

  if (replace) {
    tbody.innerHTML = "";
  }

  if (signals.length === 0 && _signalsOffset === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7">
          <div class="empty-state">
            <div class="empty-icon">📭</div>
            <p>No signals match the current filters.</p>
          </div>
        </td>
      </tr>
    `;
    moreWrap.style.display = "none";
    return;
  }

  // Apply client-side text search (title contains search string)
  const search    = _signalsFilters.search;
  const filtered  = search
    ? signals.filter((s) => (s.title ?? "").toLowerCase().includes(search))
    : signals;

  filtered.forEach((sig) => {
    tbody.appendChild(buildSignalRow(sig));
  });

  _signalsOffset += signals.length;

  // Hide "load more" if this page was smaller than limit
  _signalsExhausted = signals.length < SIGNALS_PAGE_SIZE;
  moreWrap.style.display  = _signalsExhausted ? "none" : "block";
  moreBtn.disabled        = false;
  moreBtn.textContent     = "Load more";
}

/* --------------------------------------------------------------------------
   Signal row builder
   -------------------------------------------------------------------------- */

function buildSignalRow(sig) {
  const tr = document.createElement("tr");

  // Date
  const dateCell = document.createElement("td");
  dateCell.className = "muted";
  dateCell.style.whiteSpace = "nowrap";
  dateCell.style.fontSize   = "0.78rem";
  const dateStr = sig.fetched_at
    ? new Date(sig.fetched_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
    : "—";
  dateCell.textContent = dateStr;
  tr.appendChild(dateCell);

  // Source domain (linked)
  const srcCell  = document.createElement("td");
  srcCell.style.whiteSpace = "nowrap";
  if (sig.url && sig.source_domain) {
    const a = document.createElement("a");
    a.href   = sig.url;
    a.target = "_blank";
    a.rel    = "noopener";
    a.textContent = sig.source_domain;
    srcCell.appendChild(a);
  } else {
    srcCell.textContent = sig.source_domain ?? "—";
    srcCell.className   = "muted";
  }
  tr.appendChild(srcCell);

  // Title (linked)
  const titleCell = document.createElement("td");
  titleCell.style.maxWidth = "260px";
  if (sig.url && sig.title) {
    const a = document.createElement("a");
    a.href   = sig.url;
    a.target = "_blank";
    a.rel    = "noopener";
    a.textContent  = sig.title;
    a.style.display = "block";
    a.style.overflow = "hidden";
    a.style.whiteSpace = "nowrap";
    a.style.textOverflow = "ellipsis";
    titleCell.appendChild(a);
  } else {
    titleCell.textContent = sig.title ?? "—";
    titleCell.className   = "muted";
  }
  tr.appendChild(titleCell);

  // Signal type
  const typeCell = document.createElement("td");
  typeCell.style.whiteSpace = "nowrap";
  typeCell.style.fontSize   = "0.78rem";
  typeCell.style.color      = "var(--muted-light)";
  typeCell.textContent      = sig.signal_type ?? "—";
  tr.appendChild(typeCell);

  // Relevance badge
  const relCell  = document.createElement("td");
  relCell.style.textAlign = "center";
  relCell.appendChild(buildScoreBadge(sig.relevance));
  tr.appendChild(relCell);

  // Importance badge
  const impCell  = document.createElement("td");
  impCell.style.textAlign = "center";
  impCell.appendChild(buildScoreBadge(sig.importance));
  tr.appendChild(impCell);

  // Summary (truncated)
  const sumCell = document.createElement("td");
  sumCell.className  = "summary-cell";
  sumCell.title      = sig.summary ?? "";
  sumCell.style.color = "var(--muted-light)";
  sumCell.style.fontSize = "0.8rem";
  sumCell.textContent = sig.summary ?? "—";
  tr.appendChild(sumCell);

  return tr;
}

function buildScoreBadge(score) {
  const span = document.createElement("span");
  span.className = "rel-badge";
  if (score == null) {
    span.textContent = "—";
    span.style.color = "var(--muted)";
    return span;
  }
  const pct   = Math.round(score * 100);
  const hue   = score >= 0.8 ? "#22c55e"
              : score >= 0.5 ? "#eab308"
              : "#64748b";
  span.textContent           = pct + "%";
  span.style.background      = `${hue}22`;
  span.style.color           = hue;
  span.style.border          = `1px solid ${hue}55`;
  return span;
}
