/**
 * PRISM Dashboard — Frontend JS
 * Aaryan / aaryan
 *
 * Communicates with the Flask backend via /api/* endpoints.
 * All state is sourced from the backend — nothing is hardcoded here.
 */

/* ================================================================
   State
================================================================ */
let _state = null;   // last full DashboardState from /api/state

/* ================================================================
   Boot
================================================================ */
document.addEventListener("DOMContentLoaded", () => {
  loadState();
  bindFilterListeners();
  document.getElementById("btn-refresh").addEventListener("click", () => {
    showLoadingMsg();
    fetch("/api/refresh", { method: "POST" })
      .then(r => r.json())
      .then(data => { _state = data; render(data); })
      .catch(err => showError(err));
  });
});

/* ================================================================
   Data loading
================================================================ */
function loadState() {
  showLoadingMsg();
  fetch("/api/state")
    .then(r => r.json())
    .then(data => { _state = data; render(data); })
    .catch(err => showError(err));
}

/* ================================================================
   Rendering
================================================================ */
function render(data) {
  renderOverview(data);
  renderSummary(data.summary);
  renderFindings(data.findings);
  renderFinalResults(data.final_results);
}

/* ── PR Overview ───────────────────────────────────────────────── */
function renderOverview(data) {
  setText("ov-repository",   data.pr?.repository  || "—");
  setText("ov-pull-request", data.pr?.pull_request || "—");
  setText("ov-branch",       data.pr?.branch       || "—");
  setBadge("ov-status", data.review_status);
  setBadge("ov-risk",   data.overall_risk);
  setText("ov-total", String(data.total_findings ?? "—"));
}

/* ── Finding Summary tiles ─────────────────────────────────────── */
function renderSummary(summary) {
  if (!summary) return;
  setText("sum-bugs",     String(summary.bugs     ?? 0));
  setText("sum-security", String(summary.security ?? 0));
  setText("sum-testing",  String(summary.testing  ?? 0));
  setText("sum-docs",     String(summary.documentation ?? 0));
}

/* ── Findings list ─────────────────────────────────────────────── */
function renderFindings(findings) {
  const list = document.getElementById("findings-list");
  list.innerHTML = "";

  const catFilter = document.getElementById("filter-category").value;
  const sevFilter = document.getElementById("filter-severity").value;
  const stFilter  = document.getElementById("filter-status").value;

  const filtered = (findings || []).filter(f => {
    if (catFilter !== "all" && f.category !== catFilter) return false;
    if (sevFilter !== "all" && f.severity !== sevFilter) return false;
    if (stFilter  !== "all" && f.status   !== stFilter)  return false;
    return true;
  });

  if (filtered.length === 0) {
    list.innerHTML = '<p class="loading-msg">No findings match the current filters.</p>';
    return;
  }

  const tpl = document.getElementById("tpl-finding");
  filtered.forEach(f => {
    const card = tpl.content.cloneNode(true).querySelector(".finding-card");
    card.dataset.id     = f.id;
    card.dataset.status = f.status;
    card.dataset.human  = String(!!f.requires_human_approval);

    card.querySelector(".finding-id").textContent          = f.id;
    card.querySelector(".finding-title").textContent       = f.title;
    card.querySelector(".finding-description").textContent = f.description;

    setBadgeEl(card.querySelector(".finding-category"), f.category);
    setBadgeEl(card.querySelector(".finding-severity"), f.severity);
    setBadgeEl(card.querySelector(".finding-status"),   f.status);

    // Meta rows — only show if value is present
    setMetaRow(card, "file",         f.file);
    setMetaRow(card, "line",         f.line != null ? String(f.line) : null);
    setMetaRow(card, "evidence",     f.evidence);
    setMetaRow(card, "suggested_fix",f.suggested_fix);

    // Action buttons
    card.querySelector(".btn-approve").addEventListener("click", () => {
      apiFindingAction(f.id, "approve", card);
    });
    card.querySelector(".btn-reject").addEventListener("click", () => {
      apiFindingAction(f.id, "reject", card);
    });

    list.appendChild(card);
  });
}

/* ── Final Results ─────────────────────────────────────────────── */
function renderFinalResults(res) {
  if (!res) return;
  setText("res-before",     nullish(res.findings_before));
  setText("res-after",      nullish(res.findings_after));
  setText("res-fixes",      nullish(res.fixes_applied));
  setText("res-tests-gen",  nullish(res.tests_generated));
  setText("res-tests-pass", nullish(res.tests_passed));
  setText("res-tests-fail", nullish(res.tests_failed));
  setBadge("res-pr-status", res.final_pr_status);
}

/* ================================================================
   API actions
================================================================ */
function apiFindingAction(findingId, action, cardEl) {
  fetch(`/api/findings/${encodeURIComponent(findingId)}/${action}`, { method: "POST" })
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then(data => {
      // Update card status in-place without a full re-render
      cardEl.dataset.status = data.status;
      const statusBadge = cardEl.querySelector(".finding-status");
      setBadgeEl(statusBadge, data.status);

      // Also patch the local _state so filters stay correct
      if (_state) {
        const f = (_state.findings || []).find(f => f.id === findingId);
        if (f) f.status = data.status;
        // Refresh overview counts
        refreshOverviewFromState();
      }
    })
    .catch(err => console.error("Action failed:", err));
}

function refreshOverviewFromState() {
  if (!_state) return;
  // Recompute open count for the "findings after" display
  const openCount = (_state.findings || []).filter(f => f.status === "open").length;
  const fixedCount = (_state.findings || [])
    .filter(f => f.status === "approved" || f.status === "fixed").length;
  setText("res-after",  String(openCount));
  setText("res-fixes",  String(fixedCount));

  // Recompute review_status badge approximation
  const findings = _state.findings || [];
  const hasBlocked = findings.some(f => f.requires_human_approval && f.status === "open");
  const allDone    = findings.every(f => f.status !== "open");
  const anyDone    = findings.some( f => f.status !== "open");
  let newStatus = "pending";
  if (hasBlocked)  newStatus = "blocked";
  else if (allDone) newStatus = "complete";
  else if (anyDone) newStatus = "in_progress";
  setBadge("ov-status", newStatus);
  setBadge("res-pr-status", newStatus);
}

/* ================================================================
   Filters
================================================================ */
function bindFilterListeners() {
  ["filter-category", "filter-severity", "filter-status"].forEach(id => {
    document.getElementById(id).addEventListener("change", () => {
      if (_state) renderFindings(_state.findings);
    });
  });
}

/* ================================================================
   DOM helpers
================================================================ */
function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setBadge(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  setBadgeEl(el, value);
}

function setBadgeEl(el, value) {
  if (!el || !value) return;
  // Remove any existing badge-* class
  el.className = el.className.replace(/badge-\S+/g, "").trim();
  el.classList.add("badge", `badge-${value.replace(/\s+/g, "_")}`);
  el.textContent = value.replace(/_/g, " ");
}

function setMetaRow(card, key, value) {
  const row = card.querySelector(`.meta-row[data-key="${key}"]`);
  if (!row) return;
  if (value == null || value === "") {
    row.classList.remove("visible");
    return;
  }
  row.classList.add("visible");
  const dd = row.querySelector("dd");
  if (dd) dd.textContent = value;
}

function nullish(v) {
  return v == null ? "—" : String(v);
}

function showLoadingMsg() {
  const list = document.getElementById("findings-list");
  if (list) list.innerHTML = '<p class="loading-msg">Loading findings…</p>';
}

function showError(err) {
  const list = document.getElementById("findings-list");
  if (list) list.innerHTML = `<p class="loading-msg" style="color:#ef4444">Error: ${err.message}</p>`;
}
