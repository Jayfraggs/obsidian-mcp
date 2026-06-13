/* ═══════════════════════════════════════════════════════════════════
   Obsidian MCP — Web UI
   ═══════════════════════════════════════════════════════════════════ */

"use strict";

// ── State ──────────────────────────────────────────────────────────
const S = {
  profile: "safe_write",
  blockedActions: [],
};

// ── Toast ──────────────────────────────────────────────────────────
const $toast = document.getElementById("toast");
let _toastTimer = null;

function toast(msg, type = "info", ms = 3200) {
  $toast.textContent = msg;
  $toast.className = `show ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => $toast.classList.remove("show"), ms);
}

// ── HTTP helpers ───────────────────────────────────────────────────
async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json();
  if (!res.ok) {
    const msg = data?.detail?.message || data?.detail || "Request failed";
    throw new Error(msg);
  }
  return data;
}
const GET  = (u) => api(u);
const POST = (u, b) => api(u, { method: "POST",  body: JSON.stringify(b) });
const PUT  = (u, b) => api(u, { method: "PUT",   body: JSON.stringify(b) });

function safe(fn) {
  return (...args) => fn(...args).catch((e) => toast(e.message, "error"));
}

// ── Navigation ─────────────────────────────────────────────────────
function setView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
  document.getElementById(`view-${name}`)?.classList.add("active");
  document.querySelector(`[data-view="${name}"]`)?.classList.add("active");
}

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.view));
});

// ── Tabs (per-view) ────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const container = btn.closest(".view") || btn.closest(".card") || document;
    container.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    container.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    container.getElementById
      ? container.getElementById(`tab-${btn.dataset.tab}`)?.classList.add("active")
      : document.getElementById(`tab-${btn.dataset.tab}`)?.classList.add("active");
  });
});

// Fix: tab panels need to search from document
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const section = btn.closest("section") || document;
    section.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    section.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`)?.classList.add("active");
  });
});

// ── Permission profile ─────────────────────────────────────────────
function renderPermissions(summary) {
  S.profile = summary.profile;
  S.blockedActions = summary.blocked_actions || [];
  document.getElementById("profile").value = summary.profile;

  const allowed = summary.allowed_actions || [];
  const blocked = summary.blocked_actions || [];

  document.getElementById("allowed-count").textContent = allowed.length;
  document.getElementById("blocked-count").textContent = blocked.length;
  document.getElementById("allowed-actions").innerHTML = allowed
    .map((a) => `<li class="allowed">✓ ${a}</li>`).join("");
  document.getElementById("blocked-actions").innerHTML = blocked
    .map((a) => `<li class="blocked">✗ ${a}</li>`).join("");

  const writeBlocked = S.blockedActions.includes("update_note");
  document.getElementById("save-note").disabled = writeBlocked;
}

document.getElementById("profile").addEventListener("change", async (e) => {
  try {
    const summary = await PUT("/api/permissions/profile", { profile: e.target.value });
    renderPermissions(summary);
    toast("Permission profile updated.", "success");
  } catch (err) { toast(err.message, "error"); }
});

// ── Status bar ─────────────────────────────────────────────────────
async function loadStatus() {
  const s = await GET("/api/status");
  const keyIcon = s.adapter_key_set ? "🔌" : "💾";
  document.getElementById("server-status").textContent =
    `${s.server_name}  ·  ${s.vault_path}  ·  ${keyIcon} ${s.adapter}`;
  return s;
}

// ── Notes view ─────────────────────────────────────────────────────
async function loadNotes() {
  const notes = await GET("/api/notes");
  document.getElementById("notes-list").innerHTML = notes
    .filter((p) => p.endsWith(".md"))
    .map((p) => `<li><button type="button" data-note="${p}" title="${p}">${p}</button></li>`)
    .join("") || '<li style="padding:12px;color:var(--muted);font-size:12px">No notes found.</li>';
}

async function readNote(path) {
  const note = await GET(`/api/notes/${encodeURIComponent(path)}`);
  document.getElementById("note-path").value = note.path;
  document.getElementById("note-content").value = note.content;
}

document.getElementById("refresh-notes").addEventListener("click", safe(loadNotes));

document.getElementById("notes-list").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-note]");
  if (btn) safe(readNote)(btn.dataset.note);
});

document.getElementById("save-note").addEventListener("click", safe(async () => {
  const path = document.getElementById("note-path").value.trim();
  const content = document.getElementById("note-content").value;
  if (!path) { toast("Enter a note path.", "error"); return; }
  await PUT(`/api/notes/${encodeURIComponent(path)}`, { content });
  toast("Note saved.", "success");
  await loadNotes();
}));

document.getElementById("clear-note").addEventListener("click", () => {
  document.getElementById("note-path").value = "";
  document.getElementById("note-content").value = "";
});

// ── Search view ────────────────────────────────────────────────────
document.getElementById("search-btn").addEventListener("click", safe(async () => {
  const q = document.getElementById("search-query").value.trim();
  if (!q) return;
  const results = await GET(`/api/search?q=${encodeURIComponent(q)}&limit=20`);
  const div = document.getElementById("search-results");
  if (!results.length) { div.innerHTML = '<div class="empty">No results.</div>'; return; }
  div.innerHTML = results.map((r) => `
    <div class="result-item" data-note="${r.path}">
      <span class="result-path">${r.path}</span>
      <span class="result-score">${r.score}%</span>
      <div class="result-preview">${r.preview || ""}</div>
    </div>`).join("");
}));

document.getElementById("search-results").addEventListener("click", (e) => {
  const item = e.target.closest("[data-note]");
  if (item) { safe(readNote)(item.dataset.note); setView("notes"); }
});

document.getElementById("search-query").addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("search-btn").click();
});

// ── Knowledge view ─────────────────────────────────────────────────
document.getElementById("moc-btn").addEventListener("click", safe(async () => {
  const topic = document.getElementById("moc-topic").value.trim();
  if (!topic) { toast("Enter a topic.", "error"); return; }
  const res = await POST("/api/tools/build-moc", {
    topic,
    output_path: document.getElementById("moc-path").value.trim() || null,
    limit: 20,
  });
  toast(`MOC created: ${res.path}`, "success");
  await loadNotes();
}));

document.getElementById("atomic-btn").addEventListener("click", safe(async () => {
  const path = document.getElementById("atomic-path").value.trim();
  const title = document.getElementById("atomic-title").value.trim();
  const content = document.getElementById("atomic-content").value.trim();
  if (!path || !title) { toast("Path and title required.", "error"); return; }
  const tags = document.getElementById("atomic-tags").value
    .split(",").map((t) => t.trim()).filter(Boolean);
  const res = await POST("/api/tools/create-atomic-note", { path, title, content, tags });
  toast(`Created: ${res.path}`, "success");
  await loadNotes();
}));

// ── Graph view ─────────────────────────────────────────────────────
document.getElementById("load-graph").addEventListener("click", safe(async () => {
  const data = await GET("/api/tools/relationship-graph");
  const nodes = data.nodes?.length || 0;
  const edges = data.edges?.length || 0;
  document.getElementById("graph-output").textContent =
    `Nodes: ${nodes}  ·  Edges: ${edges}\n\n` + JSON.stringify(data, null, 2);
}));

// ── Dataview view ──────────────────────────────────────────────────
document.getElementById("dv-dash-btn").addEventListener("click", safe(async () => {
  const path  = document.getElementById("dv-dash-path").value.trim();
  const title = document.getElementById("dv-dash-title").value.trim();
  if (!path || !title) { toast("Path and title required.", "error"); return; }
  const tags    = document.getElementById("dv-dash-tags").value.split(",").map(t=>t.trim()).filter(Boolean);
  const folders = document.getElementById("dv-dash-folders").value.split(",").map(t=>t.trim()).filter(Boolean);
  const res = await POST("/api/plugins/dataview/dashboard", {
    path, title, tags, folders,
    include_tasks:  document.getElementById("dv-inc-tasks").checked,
    include_recent: document.getElementById("dv-inc-recent").checked,
    include_stats:  document.getElementById("dv-inc-stats").checked,
  });
  document.getElementById("dv-dash-preview").textContent = res.content || "";
  toast(`Dashboard created: ${res.path}`, "success");
  await loadNotes();
}));

document.getElementById("dv-fields-btn").addEventListener("click", safe(async () => {
  const path = document.getElementById("dv-fields-path").value.trim();
  if (!path) { toast("Enter a note path.", "error"); return; }
  const res = await GET(`/api/plugins/dataview/fields/${encodeURIComponent(path)}`);
  document.getElementById("dv-fields-output").textContent = JSON.stringify(res, null, 2);
}));

document.getElementById("dv-q-btn").addEventListener("click", safe(async () => {
  const fields = document.getElementById("dv-q-fields").value.trim();
  if (!fields) { toast("Enter at least one field.", "error"); return; }
  const folder = document.getElementById("dv-q-folder").value.trim();
  const where  = document.getElementById("dv-q-where").value.trim();
  const sort   = document.getElementById("dv-q-sort").value.trim();
  const params = new URLSearchParams({ fields });
  if (folder) params.set("folder", folder);
  if (where)  params.set("where", where);
  if (sort)   params.set("sort", sort);
  const res = await GET(`/api/plugins/dataview/query/table?${params}`);
  const out = document.getElementById("dv-q-output");
  out.textContent = res.query;
  out.style.display = "block";
}));

document.getElementById("dv-tq-btn").addEventListener("click", safe(async () => {
  const folder = document.getElementById("dv-tq-folder").value.trim();
  const where  = document.getElementById("dv-tq-where").value.trim();
  const params = new URLSearchParams();
  if (folder) params.set("folder", folder);
  if (where)  params.set("where", where);
  const res = await GET(`/api/plugins/dataview/query/task?${params}`);
  const out = document.getElementById("dv-tq-output");
  out.textContent = res.query;
  out.style.display = "block";
}));

// ── Tasks view ─────────────────────────────────────────────────────
document.getElementById("tasks-load-btn").addEventListener("click", safe(async () => {
  const state    = document.getElementById("tasks-state-filter").value;
  const priority = document.getElementById("tasks-priority-filter").value;
  const params   = new URLSearchParams({ limit: 100 });
  if (state)    params.set("state", state);
  if (priority) params.set("priority", priority);
  const tasks = await GET(`/api/plugins/tasks/aggregate?${params}`);
  const div = document.getElementById("tasks-list");
  if (!tasks.length) { div.innerHTML = '<div class="empty">No tasks found.</div>'; return; }
  const stateIcon = { open:"⬜", done:"✅", cancelled:"❌", in_progress:"🔄" };
  div.innerHTML = tasks.map((t) => `
    <div class="task-item">
      <span class="task-state">${stateIcon[t.state] || "⬜"}</span>
      <div class="task-text">
        <div>${t.text}</div>
        <div class="task-meta">
          <span class="tag">${t.source}</span>
          ${t.due      ? `<span class="tag due">📅 ${t.due}</span>` : ""}
          ${t.priority ? `<span class="tag priority-${t.priority}">🔼 ${t.priority}</span>` : ""}
          ${t.recurrence ? `<span class="tag">🔁 ${t.recurrence}</span>` : ""}
        </div>
      </div>
    </div>`).join("");
}));

document.getElementById("tc-btn").addEventListener("click", safe(async () => {
  const note_path = document.getElementById("tc-path").value.trim();
  const text      = document.getElementById("tc-text").value.trim();
  if (!note_path || !text) { toast("Note path and task text required.", "error"); return; }
  const res = await POST("/api/plugins/tasks/create", {
    note_path, text,
    due:        document.getElementById("tc-due").value || null,
    priority:   document.getElementById("tc-priority").value || null,
    recurrence: document.getElementById("tc-recur").value.trim() || null,
    section:    document.getElementById("tc-section").value.trim() || null,
  });
  const out = document.getElementById("tc-result");
  out.textContent = res.task;
  out.style.display = "block";
  toast("Task added.", "success");
}));

document.getElementById("tn-btn").addEventListener("click", safe(async () => {
  const path  = document.getElementById("tn-path").value.trim();
  const title = document.getElementById("tn-title").value.trim();
  if (!path || !title) { toast("Path and title required.", "error"); return; }
  const raw = document.getElementById("tn-tasks").value.trim();
  const tasks = raw.split("\n").filter(Boolean).map((line) => {
    const parts = line.split("|").map((s) => s.trim());
    const obj = { text: parts[0] };
    parts.slice(1).forEach((kv) => {
      const [k, v] = kv.split("=").map((s) => s.trim());
      if (k && v) obj[k] = v;
    });
    return obj;
  });
  const tags = document.getElementById("tn-tags").value.split(",").map(t=>t.trim()).filter(Boolean);
  const area = document.getElementById("tn-area").value.trim();
  const res = await POST("/api/plugins/tasks/note", { path, title, tasks, tags, area });
  toast(`Task note created: ${res.path}`, "success");
  await loadNotes();
}));

// ── Templater view ─────────────────────────────────────────────────
async function loadTemplates() {
  const templates = await GET("/api/plugins/templater/list");
  document.getElementById("tpl-list").innerHTML = templates
    .map((t) => `<li><button type="button" data-tpl="${t.path}" title="${t.path}">${t.name}</button></li>`)
    .join("") || '<li style="padding:12px;color:var(--muted);font-size:12px">No templates found.</li>';
}

document.getElementById("tpl-refresh").addEventListener("click", safe(loadTemplates));

document.getElementById("tpl-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-tpl]");
  if (!btn) return;
  try {
    const res = await GET(`/api/plugins/templater/read/${encodeURIComponent(btn.dataset.tpl)}`);
    document.getElementById("tpl-preview").textContent = res.content || "(empty)";
  } catch (err) { toast(err.message, "error"); }
});

document.getElementById("tpl-apply-btn").addEventListener("click", safe(async () => {
  const template_name = document.getElementById("tpl-apply-name").value.trim();
  const output_path   = document.getElementById("tpl-apply-output").value.trim();
  if (!template_name || !output_path) { toast("Template name and output path required.", "error"); return; }
  let variables = null;
  const varsRaw = document.getElementById("tpl-apply-vars").value.trim();
  if (varsRaw) { try { variables = JSON.parse(varsRaw); } catch { toast("Variables must be valid JSON.", "error"); return; } }
  const res = await POST("/api/plugins/templater/apply", {
    template_name, output_path, variables,
    title: document.getElementById("tpl-apply-title").value.trim() || null,
  });
  toast(`Note created: ${res.path}`, "success");
  await loadNotes();
}));

document.getElementById("tpl-new-btn").addEventListener("click", safe(async () => {
  const name = document.getElementById("tpl-new-name").value.trim();
  if (!name) { toast("Template name required.", "error"); return; }
  const tags = document.getElementById("tpl-new-tags").value.split(",").map(t=>t.trim()).filter(Boolean);
  const custom_fields = document.getElementById("tpl-new-fields").value.split(",").map(t=>t.trim()).filter(Boolean);
  const res = await POST("/api/plugins/templater/create", {
    name,
    template_type: document.getElementById("tpl-new-type").value,
    tags,
    custom_fields,
  });
  toast(`Template created: ${res.path}`, "success");
  await loadTemplates();
}));

// ── Excalidraw view ────────────────────────────────────────────────
function parseNodes(raw) {
  return raw.split("\n").filter(Boolean).map((line) => {
    const parts = line.split("|").map((s) => s.trim());
    return { id: parts[0], label: parts[1] || parts[0], type: parts[2] || "service" };
  });
}

function parseEdges(raw) {
  return raw.split("\n").filter(Boolean).map((line) => {
    const [left, labelPart] = line.split("|").map((s) => s.trim());
    const arrow = left.includes("→") ? "→" : "->";
    const [from, to] = left.split(arrow).map((s) => s.trim());
    return { from, to, label: labelPart || "" };
  });
}

document.getElementById("ex-arch-btn").addEventListener("click", safe(async () => {
  const path  = document.getElementById("ex-arch-path").value.trim();
  const title = document.getElementById("ex-arch-title").value.trim();
  if (!path || !title) { toast("Path and title required.", "error"); return; }
  const nodes  = parseNodes(document.getElementById("ex-arch-nodes").value);
  const edges  = parseEdges(document.getElementById("ex-arch-edges").value);
  const layout = document.getElementById("ex-arch-layout").value;
  const res = await POST("/api/plugins/excalidraw/architecture", { path, title, nodes, edges, layout });
  toast(`Diagram created: ${res.path}`, "success");
  await loadNotes();
}));

function parseBranches(raw) {
  return raw.split("\n").filter(Boolean).map((line) => {
    const [label, childrenRaw] = line.split("|").map((s) => s.trim());
    const children = childrenRaw ? childrenRaw.split(",").map((s) => s.trim()).filter(Boolean) : [];
    return { label, children };
  });
}

document.getElementById("ex-con-btn").addEventListener("click", safe(async () => {
  const path           = document.getElementById("ex-con-path").value.trim();
  const central_concept = document.getElementById("ex-con-central").value.trim();
  if (!path || !central_concept) { toast("Path and central concept required.", "error"); return; }
  const branches = parseBranches(document.getElementById("ex-con-branches").value);
  const res = await POST("/api/plugins/excalidraw/concept-map", { path, central_concept, branches });
  toast(`Concept map created: ${res.path}`, "success");
  await loadNotes();
}));

document.getElementById("ex-parse-btn").addEventListener("click", safe(async () => {
  const path = document.getElementById("ex-parse-path").value.trim();
  if (!path) { toast("Enter a note path.", "error"); return; }
  const res = await GET(`/api/plugins/excalidraw/parse/${encodeURIComponent(path)}`);
  document.getElementById("ex-parse-output").textContent =
    `Elements: ${res.element_count}\n\n` + JSON.stringify(res.elements, null, 2);
}));

// ── Omnisearch view ────────────────────────────────────────────────
document.getElementById("om-opt-btn").addEventListener("click", safe(async () => {
  const path = document.getElementById("om-opt-path").value.trim();
  if (!path) { toast("Enter a note path.", "error"); return; }
  const res = await GET(`/api/plugins/omnisearch/optimise/${encodeURIComponent(path)}`);
  const div = document.getElementById("om-opt-result");

  const aliasHTML = res.alias_suggestions.length
    ? res.alias_suggestions.map((a) => `<span class="tag" style="margin:2px">${a}</span>`).join(" ")
    : '<span style="color:var(--muted)">None suggested</span>';

  const kwHTML = res.keyword_suggestions.length
    ? res.keyword_suggestions.map((k) =>
        `<div class="task-item"><span class="task-text"><b>${k.keyword}</b> <span style="color:var(--muted);font-size:11px">×${k.frequency}</span></span></div>`
      ).join("")
    : '<div class="empty">No keyword gaps found.</div>';

  div.innerHTML = `
    <div class="card" style="margin-top:0">
      <div class="card-title">Suggested aliases</div>
      <div style="margin-bottom:10px">${aliasHTML}</div>
      ${res.alias_suggestions.length ? `
      <button class="btn-primary btn-sm" id="om-apply-aliases">Add all aliases</button>` : ""}
    </div>
    <div class="card">
      <div class="card-title">Keyword gaps</div>
      <div style="border:1px solid var(--border);border-radius:var(--radius)">${kwHTML}</div>
    </div>
    <p style="font-size:12px;color:var(--muted);margin-top:8px">${res.tip}</p>`;

  document.getElementById("om-apply-aliases")?.addEventListener("click", safe(async () => {
    await POST("/api/plugins/omnisearch/add-aliases", { path, aliases: res.alias_suggestions });
    toast("Aliases added.", "success");
  }));
}));

document.getElementById("om-bulk-btn").addEventListener("click", safe(async () => {
  const results = await GET("/api/plugins/omnisearch/poorly-indexed?limit=30");
  const div = document.getElementById("om-bulk-result");
  if (!results.length) { div.innerHTML = '<div class="empty">All notes look well indexed! 🎉</div>'; return; }
  div.innerHTML = `
    <div style="border:1px solid var(--border);border-radius:var(--radius)">
      ${results.map((r) => `
      <div class="task-item">
        <div class="task-text">
          <div style="font-size:12px;font-weight:500;color:var(--accent)">${r.path}</div>
          <div class="task-meta">${r.issues.map((i) => `<span class="tag">${i}</span>`).join("")}</div>
        </div>
        <button class="btn-sm" onclick="safe(async()=>{
          document.getElementById('om-opt-path').value='${r.path}';
          document.getElementById('om-opt-btn').click();
          setView('omnisearch');
          document.querySelector('[data-tab=om-optimise]').click();
        })()">Analyse</button>
      </div>`).join("")}
    </div>`;
}));

// ── Permissions view ───────────────────────────────────────────────
async function loadPermissions() {
  const summary = await GET("/api/permissions/profile");
  renderPermissions(summary);
}

// ── Settings view ──────────────────────────────────────────────────
async function loadAdapterSettings() {
  const s = await GET("/api/settings/adapter");
  if (s.key_set) {
    document.getElementById("adapter-key").placeholder = `Key set (${s.key_preview})`;
  }
  document.getElementById("adapter-host").value = s.host;
  document.getElementById("adapter-port").value = s.port;
}

async function loadServerInfo() {
  const s = await GET("/api/status");
  document.getElementById("settings-server-info").textContent = JSON.stringify(s, null, 2);
}

// Show/hide key
document.getElementById("key-toggle").addEventListener("click", () => {
  const inp = document.getElementById("adapter-key");
  const btn = document.getElementById("key-toggle");
  const isHidden = inp.type === "password";
  inp.type = isHidden ? "text" : "password";
  btn.textContent = isHidden ? "Hide" : "Show";
});

document.getElementById("adapter-save-btn").addEventListener("click", safe(async () => {
  const api_key = document.getElementById("adapter-key").value.trim();
  const host    = document.getElementById("adapter-host").value.trim() || "127.0.0.1";
  const port    = parseInt(document.getElementById("adapter-port").value) || 27123;
  await PUT("/api/settings/adapter", { api_key, host, port });
  toast("Connection settings saved.", "success");
  await loadStatus();
  await loadServerInfo();
}));

document.getElementById("adapter-test-btn").addEventListener("click", safe(async () => {
  const dot  = document.getElementById("adapter-dot");
  const text = document.getElementById("adapter-status-text");
  dot.className  = "status-dot grey";
  text.textContent = "Testing…";
  const res = await POST("/api/settings/adapter/test", {});
  dot.className  = `status-dot ${res.reachable ? "green" : "red"}`;
  text.textContent = res.reachable ? "Connected ✓" : `Unreachable — ${res.reason}`;
  toast(res.reachable ? "REST API reachable." : res.reason, res.reachable ? "success" : "error");
}));

document.getElementById("adapter-clear-btn").addEventListener("click", safe(async () => {
  document.getElementById("adapter-key").value = "";
  await PUT("/api/settings/adapter", { api_key: "", host: "127.0.0.1", port: 27123 });
  document.getElementById("adapter-dot").className = "status-dot grey";
  document.getElementById("adapter-status-text").textContent = "Key cleared";
  toast("API key cleared.", "success");
  await loadStatus();
}));

// ── AI Rules view ──────────────────────────────────────────────────
const RULE_PRESETS = {
  homelab: `Store all infrastructure notes under the HomeLab/ folder.
Tag every infrastructure note with #home-lab and a sub-tag like #home-lab/proxmox.
Always include an Architecture section in system notes.
Link new service notes to [[MOC - Home Infrastructure]].
Use the system template for any new service or tool note.`,
  zettelkasten: `Every note must contain exactly one idea (atomic notes only).
Always assign a unique numeric ID prefix to note filenames.
New notes must link to at least one existing note — no orphans.
Use MOC notes to organise clusters of related ideas.
Tags should be sparse — only add a tag if it describes a meaningful category.`,
  gtd: `All tasks must have a due date and a priority.
Capture notes go in Inbox/ — do not create notes directly in project folders.
Review notes in Inbox/ and move them during weekly review.
Every project must have a dedicated note with a task list.
Use the project template for all project notes.`,
  safe: `Never create, update, or delete any file without explicit user instruction.
Do not infer intent — always confirm before writing.
Treat all vault operations as read-only unless the user explicitly says to write.
Never append to existing notes without showing the user what will be added first.`,
};

async function loadRules() {
  const res = await GET("/api/rules");
  document.getElementById("rules-textarea").value = res.rules || "";
  updateRulesCount();
  updateRulesPreview(res.rules);
}

function updateRulesCount() {
  const lines = document.getElementById("rules-textarea").value
    .split("\n").filter((l) => l.trim() && !l.startsWith("#")).length;
  document.getElementById("rules-count").textContent = lines;
}

async function updateRulesPreview(rules) {
  try {
    const res = await GET("/api/rules/system-prompt");
    document.getElementById("rules-preview").textContent = res.system_prompt;
  } catch { /* non-fatal */ }
}

document.getElementById("rules-textarea").addEventListener("input", () => {
  updateRulesCount();
});

document.getElementById("rules-save-btn").addEventListener("click", safe(async () => {
  const rules = document.getElementById("rules-textarea").value;
  const res = await PUT("/api/rules", { rules });
  document.getElementById("rules-status").textContent =
    `Saved ${res.rule_count} rule${res.rule_count !== 1 ? "s" : ""}.`;
  toast(`${res.rule_count} rules saved.`, "success");
  await updateRulesPreview(rules);
}));

document.getElementById("rules-reset-btn").addEventListener("click", safe(async () => {
  await loadRules();
  toast("Rules reloaded from disk.", "info");
}));

document.getElementById("rule-presets").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-preset]");
  if (!btn) return;
  const preset = RULE_PRESETS[btn.dataset.preset];
  if (!preset) return;
  const ta = document.getElementById("rules-textarea");
  ta.value = ta.value.trim()
    ? ta.value.trimEnd() + "\n\n# " + btn.dataset.preset + " preset\n" + preset
    : preset;
  updateRulesCount();
  toast(`"${btn.dataset.preset}" rules appended.`, "success");
});

// ── Initialise ─────────────────────────────────────────────────────
(async () => {
  try {
    await Promise.all([
      loadStatus(),
      loadPermissions(),
      loadNotes(),
      loadTemplates(),
      loadAdapterSettings(),
      loadServerInfo(),
      loadRules(),
    ]);
  } catch (e) {
    toast(e.message, "error");
  }
})();
