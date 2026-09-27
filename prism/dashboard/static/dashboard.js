/**
 * PreVise Dashboard — Frontend JS v5
 * Communicates with the Flask backend via /api/* endpoints.
 */

let _state = null;

/* ── Boot ───────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  loadState();
  bindConfigBar();
  bindFilterListeners();
  bindNavItems();

  document.getElementById("btn-refresh").addEventListener("click", () => {
    showLoading();
    fetch("/api/refresh", { method: "POST" })
      .then(r => r.json())
      .then(data => { _state = data; render(data); })
      .catch(showError);
  });
});

/* ── Nav items (scroll-to section) ─────────────────────────── */
function bindNavItems() {
  document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
      item.classList.add("active");
      const id = "section-" + item.dataset.section;
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

/* ── Config panel ───────────────────────────────────────────── */
function bindConfigBar() {
  const bar    = document.getElementById("config-bar");
  const btnCfg = document.getElementById("btn-config");
  const btnClose = document.getElementById("btn-close-config");

  btnCfg.addEventListener("click", () => {
    const open = bar.style.display !== "none";
    bar.style.display = open ? "none" : "block";
    btnCfg.textContent = open ? "Configure" : "✕ Close";
  });

  if (btnClose) btnClose.addEventListener("click", () => {
    bar.style.display = "none";
    btnCfg.textContent = "Configure";
  });

  document.getElementById("config-form").addEventListener("submit", e => {
    e.preventDefault();
    const btn   = document.getElementById("btn-run");
    const errEl = document.getElementById("config-error");
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
        bar.style.display = "none";
        btnCfg.textContent = "Configure";
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

/* ── Load ───────────────────────────────────────────────────── */
function loadState() {
  showLoading();
  fetch("/api/state")
    .then(r => r.json())
    .then(data => { _state = data; render(data); })
    .catch(showError);
}

/* ── Render ─────────────────────────────────────────────────── */
function render(data) {
  renderHero(data);
  renderSummary(data.summary);
  renderFindings(data.findings);
  renderFinalResults(data.final_results);
}

function renderHero(data) {
  setText("ov-repo-root",    data.repo_root || ".");
  setText("ov-repository",   data.pr?.repository  || "—");
  setText("ov-pull-request", data.pr?.pull_request || "—");
  setText("ov-branch",       data.pr?.branch       || "—");
  setText("ov-total",        String(data.total_findings ?? "—"));
  setBadge("ov-status", data.review_status);
  setBadge("ov-risk",   data.overall_risk);

  // Pre-fill config inputs
  const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v || ""; };
  setVal("cfg-repo",   data.pr?.repository);
  setVal("cfg-pr",     data.pr?.pull_request);
  setVal("cfg-branch", data.pr?.branch);
  setVal("cfg-author", data.pr?.author);
  setVal("cfg-root",   data.repo_root || ".");
}

function renderSummary(s) {
  if (!s) return;
  setText("sum-security", String(s.security      ?? 0));
  setText("sum-bugs",     String(s.bugs          ?? 0));
  setText("sum-testing",  String(s.testing       ?? 0));
  setText("sum-docs",     String(s.documentation ?? 0));
}

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
    list.innerHTML = '<p class="empty-msg">No findings match the current filters.</p>';
    return;
  }

  const tpl = document.getElementById("tpl-finding");
  filtered.forEach(f => {
    const card = tpl.content.cloneNode(true).querySelector(".finding-card");

    card.dataset.id       = f.id;
    card.dataset.status   = f.status;
    card.dataset.severity = f.severity;
    card.dataset.human    = String(!!f.requires_human_approval);

    card.querySelector(".finding-id").textContent    = f.id;
    card.querySelector(".finding-title").textContent = f.title;

    setBadgeEl(card.querySelector(".finding-severity"), f.severity);
    setBadgeEl(card.querySelector(".finding-category"), f.category);
    setBadgeEl(card.querySelector(".finding-status"),   f.status);

    // Location
    const locFile = card.querySelector(".finding-file");
    const locLine = card.querySelector(".finding-line");
    if (f.file) locFile.textContent = f.file;
    else locFile.style.display = "none";
    if (f.line != null) locLine.textContent = f.line;
    else locLine.closest(".loc-line").style.display = "none";

    // Evidence block
    const evBlock = card.querySelector(".finding-evidence-block");
    if (f.evidence) {
      card.querySelector(".finding-evidence").textContent = f.evidence;
      evBlock.classList.add("visible");
    }

    // Fix block
    const fixBlock = card.querySelector(".finding-fix-block");
    if (f.suggested_fix) {
      card.querySelector(".finding-fix").textContent = f.suggested_fix;
      fixBlock.classList.add("visible");
    }

    // Actions
    card.querySelector(".btn-approve").addEventListener("click", () => apiFindingAction(f.id, "approve", card));
    card.querySelector(".btn-reject").addEventListener("click",  () => apiFindingAction(f.id, "reject",  card));

    list.appendChild(card);
  });
}

function renderFinalResults(res) {
  if (!res) return;
  setText("res-before",     nullish(res.findings_before));
  setText("res-after",      nullish(res.findings_after));
  setText("res-fixes",      nullish(res.fixes_applied));
  // Tests: null means "no tests/ dir found", 0 means ran but none
  setText("res-tests-gen",  res.tests_generated == null ? "—" : String(res.tests_generated));
  setText("res-tests-pass", res.tests_passed    == null ? "—" : String(res.tests_passed));
  setText("res-tests-fail", res.tests_failed    == null ? "—" : String(res.tests_failed));
  setBadge("res-pr-status", res.final_pr_status);
}

/* ── API actions ────────────────────────────────────────────── */
function apiFindingAction(id, action, cardEl) {
  fetch(`/api/findings/${encodeURIComponent(id)}/${action}`, { method: "POST" })
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then(data => {
      cardEl.dataset.status = data.status;
      setBadgeEl(cardEl.querySelector(".finding-status"), data.status);
      if (_state) {
        const f = (_state.findings || []).find(f => f.id === id);
        if (f) f.status = data.status;
        refreshOverview();
      }
    })
    .catch(err => console.error("Action failed:", err));
}

function refreshOverview() {
  if (!_state) return;
  const all     = _state.findings || [];
  const open    = all.filter(f => f.status === "open").length;
  const fixed   = all.filter(f => f.status === "approved" || f.status === "fixed").length;
  setText("res-after", String(open));
  setText("res-fixes", String(fixed));

  const hasBlocked = all.some(f => f.requires_human_approval && f.status === "open");
  const allDone    = all.every(f => f.status !== "open");
  const anyDone    = all.some( f => f.status !== "open");
  let status = "pending";
  if (hasBlocked)   status = "blocked";
  else if (allDone) status = "complete";
  else if (anyDone) status = "in_progress";
  setBadge("ov-status",    status);
  setBadge("res-pr-status", status);
}

/* ── Filters ────────────────────────────────────────────────── */
function bindFilterListeners() {
  ["filter-category", "filter-severity", "filter-status"].forEach(id => {
    document.getElementById(id).addEventListener("change", () => {
      if (_state) renderFindings(_state.findings);
    });
  });
}

/* ── DOM helpers ────────────────────────────────────────────── */
function setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }

function setBadge(id, v) { const el = document.getElementById(id); if (el) setBadgeEl(el, v); }

function setBadgeEl(el, v) {
  if (!el || !v) return;
  el.className = el.className.replace(/badge-\S+/g, "").trim();
  el.classList.add("badge", `badge-${v.replace(/\s+/g, "_")}`);
  el.textContent = v.replace(/_/g, " ");
}

function nullish(v) { return v == null ? "—" : String(v); }

function showLoading() {
  const list = document.getElementById("findings-list");
  if (list) list.innerHTML = `
    <div class="loading-state">
      <div class="loading-spinner"></div>
      <span>Running agents…</span>
    </div>`;
}

function showError(err) {
  const list = document.getElementById("findings-list");
  if (list) list.innerHTML = `<p class="empty-msg" style="color:#f87171">Error: ${err.message}</p>`;
}
