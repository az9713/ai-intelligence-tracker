/**
 * memos.js — Memos tab: left rail week list + markdown memo viewer.
 */

let _currentMemoMarkdown = "";
let _currentMemoWeek     = "";
let _memosLoaded         = false;

window.loadTab_memos = async function loadTab_memos() {
  // Only re-fetch the list once per session; re-opening the tab just re-uses it.
  if (!_memosLoaded) {
    await loadMemoList();
    _memosLoaded = true;
  }
};

/* --------------------------------------------------------------------------
   Memo list (left rail)
   -------------------------------------------------------------------------- */

async function loadMemoList() {
  const listEl = document.getElementById("memo-list");
  window.renderLoader(listEl);

  let memos = null;
  try {
    memos = await window.apiFetch("/api/memos");
  } catch (err) {
    console.error("Memos list fetch error:", err);
    window.renderEmpty(listEl, "Failed to load memo list.");
    return;
  }

  if (!memos || memos.length === 0) {
    window.renderEmpty(listEl, "No memos yet — run the collection.");
    return;
  }

  listEl.innerHTML = memos.map((m) => `
    <div class="memo-list-item" data-week="${window.escapeHtml(m.iso_week)}">
      <div class="memo-week">${window.escapeHtml(m.iso_week)}</div>
      <div class="memo-signal">${window.escapeHtml(m.strongest_signal ?? "")}</div>
    </div>
  `).join("");

  listEl.querySelectorAll(".memo-list-item").forEach((item) => {
    item.addEventListener("click", () => {
      listEl.querySelectorAll(".memo-list-item").forEach((i) => i.classList.remove("active"));
      item.classList.add("active");
      loadMemoContent(item.dataset.week);
    });
  });

  // Auto-load the latest (first in list)
  const firstItem = listEl.querySelector(".memo-list-item");
  if (firstItem) {
    firstItem.classList.add("active");
    loadMemoContent(firstItem.dataset.week);
  }
}

/* --------------------------------------------------------------------------
   Memo content area
   -------------------------------------------------------------------------- */

async function loadMemoContent(week) {
  const contentEl = document.getElementById("memo-content");
  _currentMemoMarkdown = "";
  _currentMemoWeek     = week;

  contentEl.innerHTML = `<div class="loader">Loading memo for ${window.escapeHtml(week)}…</div>`;

  let memo = null;
  try {
    memo = await window.apiFetch(`/api/memo?week=${encodeURIComponent(week)}`);
  } catch (err) {
    console.error("Memo content fetch error:", err);
    window.renderEmpty(contentEl, `Failed to load memo for ${week}.`);
    return;
  }

  if (!memo || !memo.full_markdown) {
    window.renderEmpty(contentEl, `No memo content available for ${week}.`);
    return;
  }

  _currentMemoMarkdown = memo.full_markdown;

  // Parse markdown — marked.js must be loaded
  let htmlContent = "";
  if (typeof marked !== "undefined") {
    // marked v4+ uses marked.parse(); older versions are called directly
    const parseFn = marked.parse ?? marked;
    htmlContent = parseFn(_currentMemoMarkdown);
  } else {
    // Fallback: plain text in a <pre>
    htmlContent = `<pre>${window.escapeHtml(_currentMemoMarkdown)}</pre>`;
  }

  contentEl.innerHTML = `
    <div class="memo-toolbar">
      <h2>${window.escapeHtml(week)}</h2>
      <button class="btn btn-secondary btn-sm" id="memo-export-btn">Export .md</button>
    </div>
    <div class="md-content">${htmlContent}</div>
  `;

  document.getElementById("memo-export-btn").addEventListener("click", () => {
    exportMarkdown(_currentMemoMarkdown, _currentMemoWeek);
  });
}

/* --------------------------------------------------------------------------
   Export markdown as a file download
   -------------------------------------------------------------------------- */

function exportMarkdown(markdown, week) {
  const blob     = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url      = URL.createObjectURL(blob);
  const anchor   = document.createElement("a");
  anchor.href     = url;
  anchor.download = `memo-${week}.md`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
