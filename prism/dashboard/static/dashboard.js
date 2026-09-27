/**
 * PRISM Dashboard — Frontend JS
 * Communicates with the Flask backend via /api/* endpoints.
 * All state is sourced from the backend — nothing is hardcoded here.
 */

/* ================================================================
   State
================================================================ */
let _state = null;

/* ================================================================
   Boot
================================================================ */
document.addEventListener("DOMContentLoaded", () => {
  loadState();
  bindConfigBar();
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
   Config bar
================================================================ */
function bindConfigBar() {
  // Toggle open/close
  document.getElementById("btn-config").addEventListener("click", () => {
    const bar = document.getElementById("config-bar");
    const open = bar.style.display !== "none";
    bar.style.display = open ? "none" : "block";
    document.getElementById("btn-config").textContent = open ? "⚙ Configure" : "✕ Close";
  });

  // Submit — post to /api/configure, re-render
  document.getElementById("config-form").addEventListener("submit", e => {
    e.preventDefault();
    const btn    = document.getElementById("btn-run");
    const errEl  = document.getElementById("config-error");
    errEl.style.display = "none";
    btn.disabled = true;
    btn.textContent = "Running…";

    const payload = {
      repository:   document.getElementById("cfg-repo").value.trim(),
      pull_request: document.getElementById("cfg-pr").value.trim(),
      branch:       document.getElementById("cfg-branch").value.trim(),
      author:       document.getElementById("cfg-author").value.trim(),
      repo_root:    document.getElementById("cfg-root").value.trim() || ".",
    };

    fetch("/api/configure", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(r => {
        if (!r.ok) return r.json().then(d => { throw new Error(d.error || `HTTP ${r.status}`); });
        return r.json();
      })
      .then(data => {
        _state = data;
        render(data);
        // Collapse the bar after a successful run
        document.getElementById("config-bar").style.display = "none";
        document.getElementById("btn-config").textContent = "⚙ Configure";
      })
      .catch(err => {
        errEl.textContent = "Error: " + err.message;
        errEl.style.display = "inline";
      })
      .finally(() => {
        btn.disabled = false;
        btn.textContent = "▶ Run Review";
      });
  });
}

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

  // Pre-fill config inputs with current values (guard against null in case bar not yet in DOM)
  const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
  setVal("cfg-repo",   data.pr?.repository  || "");
  setVal("cfg-pr",     data.pr?.pull_request || "");
  setVal("cfg-branch", data.pr?.branch       || "");
  setVal("cfg-author", data.pr?.author       || "");
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

    setMetaRow(card, "file",         f.file);
    setMetaRow(card, "line",         f.line != null ? String(f.line) : null);
    setMetaRow(card, "evidence",     f.evidence);
    setMetaRow(card, "suggested_fix",f.suggested_fix);

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
      cardEl.dataset.status = data.status;
      const statusBadge = cardEl.querySelector(".finding-status");
      setBadgeEl(statusBadge, data.status);
      if (_state) {
        const f = (_state.findings || []).find(f => f.id === findingId);
        if (f) f.status = data.status;
        refreshOverviewFromState();
      }
    })
    .catch(err => console.error("Action failed:", err));
}

function refreshOverviewFromState() {
  if (!_state) return;
  const openCount  = (_state.findings || []).filter(f => f.status === "open").length;
  const fixedCount = (_state.findings || [])
    .filter(f => f.status === "approved" || f.status === "fixed").length;
  setText("res-after", String(openCount));
  setText("res-fixes", String(fixedCount));

  const findings   = _state.findings || [];
  const hasBlocked = findings.some(f => f.requires_human_approval && f.status === "open");
  const allDone    = findings.every(f => f.status !== "open");
  const anyDone    = findings.some( f => f.status !== "open");
  let newStatus = "pending";
  if (hasBlocked)   newStatus = "blocked";
  else if (allDone) newStatus = "complete";
  else if (anyDone) newStatus = "in_progress";
  setBadge("ov-status",    newStatus);
  setBadge("res-pr-status",newStatus);
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
  el.className = el.className.replace(/badge-\S+/g, "").trim();
  el.classList.add("badge", `badge-${value.replace(/\s+/g, "_")}`);
  el.textContent = value.replace(/_/g, " ");
}

function setMetaRow(card, key, value) {
  const row = card.querySelector(`.meta-row[data-key="${key}"]`);
  if (!row) return;
  if (value == null || value === "") { row.classList.remove("visible"); return; }
  row.classList.add("visible");
  const dd = row.querySelector("dd");
  if (dd) dd.textContent = value;
}

function nullish(v) { return v == null ? "—" : String(v); }

function showLoadingMsg() {
  const list = document.getElementById("findings-list");
  if (list) list.innerHTML = '<p class="loading-msg">Loading findings…</p>';
}

function showError(err) {
  const list = document.getElementById("findings-list");
  if (list) list.innerHTML = `<p class="loading-msg" style="color:#ef4444">Error: ${err.message}</p>`;
}
