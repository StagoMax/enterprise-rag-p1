const state = {
  role: localStorage.getItem("rag-role") || "engineering",
  token: null,
  traceId: null,
  view: "query",
};

const viewMeta = {
  query: ["QUERY", "知识查询"],
  knowledge: ["KNOWLEDGE", "知识资产"],
  evaluation: ["EVALUATION", "基线评测"],
  audit: ["AUDIT", "审计记录"],
};

const routeLabels = {
  rag: "RAG",
  exact_search: "精确检索",
  tool: "SQL / API",
  handoff_or_refuse: "拒答 / 转交",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.hidden = true; }, 3600);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* no json */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

async function issueToken() {
  const result = await api("/dev/token", {
    method: "POST",
    body: JSON.stringify({ subject: "workbench-user", roles: [state.role], tenant_id: "demo" }),
  });
  state.token = result.access_token;
}

async function refreshHealth() {
  try {
    const health = await api("/health");
    $("#status-dot").className = "status-dot is-online";
    $("#service-label").textContent = "服务正常";
    $("#document-count").textContent = health.documents;
    $("#embedding-backend").textContent = health.embedding_backend;
  } catch (error) {
    $("#status-dot").className = "status-dot is-offline";
    $("#service-label").textContent = "服务不可用";
  }
}

async function loadSamples() {
  const container = $("#sample-row");
  container.replaceChildren();
  try {
    const samples = await api("/v1/samples");
    for (const sample of samples.slice(0, 4)) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = sample.question.replace(/\s+/g, " ");
      button.title = sample.question;
      button.addEventListener("click", () => {
        $("#question").value = sample.question;
        $("#question").focus();
      });
      container.append(button);
    }
  } catch (error) {
    container.replaceChildren();
  }
}

function setLoading(loading) {
  $("#query-empty").hidden = true;
  $("#query-result").hidden = true;
  $("#query-loading").hidden = !loading;
  $(".result-region").setAttribute("aria-busy", String(loading));
  $("#submit-query").disabled = loading;
}

function renderCitations(citations) {
  const list = $("#citation-list");
  list.replaceChildren();
  if (!citations.length) {
    const item = document.createElement("li");
    item.textContent = "无引用";
    list.append(item);
    return;
  }
  citations.forEach((citation, index) => {
    const item = document.createElement("li");
    const number = document.createElement("span");
    number.className = "citation-index";
    number.textContent = String(index + 1);
    const body = document.createElement("div");
    const title = document.createElement("div");
    title.className = "citation-title";
    title.textContent = citation.title;
    const detail = document.createElement("div");
    detail.className = "citation-detail";
    detail.textContent = [citation.source_id, citation.version, citation.anchor].filter(Boolean).join(" · ");
    body.append(title, detail);
    const score = document.createElement("span");
    score.className = "citation-score";
    score.textContent = citation.score == null ? "" : Number(citation.score).toFixed(3);
    item.append(number, body, score);
    list.append(item);
  });
}

function renderQueryResult(result) {
  state.traceId = result.trace_id;
  $("#query-loading").hidden = true;
  $("#query-result").hidden = false;
  const badge = $("#route-badge");
  badge.textContent = routeLabels[result.route] || result.route;
  badge.classList.toggle("is-refused", result.refused);
  $("#route-reason").textContent = result.route_reason;
  $("#answer-text").textContent = result.answer;
  $("#trace-id").textContent = result.trace_id;
  renderCitations(result.citations);
}

async function submitQuery(event) {
  event.preventDefault();
  const question = $("#question").value.trim();
  if (!question) return;
  setLoading(true);
  try {
    const result = await api("/v1/query", {
      method: "POST",
      body: JSON.stringify({ question }),
    });
    renderQueryResult(result);
  } catch (error) {
    $("#query-loading").hidden = true;
    $("#query-empty").hidden = false;
    $("#query-empty").textContent = `查询失败：${error.message}`;
  } finally {
    $("#submit-query").disabled = false;
    $(".result-region").setAttribute("aria-busy", "false");
  }
}

async function submitFeedback(rating) {
  if (!state.traceId) return;
  try {
    await api("/v1/feedback", {
      method: "POST",
      body: JSON.stringify({ trace_id: state.traceId, rating }),
    });
    showToast("反馈已记录");
  } catch (error) {
    showToast(`反馈失败：${error.message}`);
  }
}

function showInlineError(selector, message) {
  const element = $(selector);
  element.textContent = message;
  element.hidden = !message;
}

async function loadKnowledge() {
  const body = $("#knowledge-table tbody");
  body.replaceChildren();
  $("#ingest-form").hidden = state.role !== "knowledge_admin";
  try {
    const documents = await api("/v1/knowledge");
    $("#knowledge-count").textContent = documents.length;
    showInlineError("#knowledge-error", "");
    for (const knowledgeDocument of documents) {
      const row = document.createElement("tr");
      [knowledgeDocument.title, knowledgeDocument.business_class, knowledgeDocument.version, knowledgeDocument.owner].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value || "-";
        row.append(cell);
      });
      body.append(row);
    }
  } catch (error) {
    showInlineError("#knowledge-error", `加载失败：${error.message}`);
  }
}

async function submitIngest(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = {
    document_id: form.get("document_id"),
    title: form.get("title"),
    owner: form.get("owner"),
    business_class: form.get("business_class"),
    allowed_roles: [form.get("allowed_role")],
    version: form.get("version"),
    content: form.get("content"),
  };
  try {
    await api("/v1/documents", { method: "POST", body: JSON.stringify(payload) });
    event.currentTarget.reset();
    showToast("文档已发布");
  } catch (error) {
    showToast(`发布失败：${error.message}`);
  }
}

function percent(value) { return `${(Number(value) * 100).toFixed(1)}%`; }

async function loadEvaluation() {
  const strip = $("#metric-strip");
  strip.replaceChildren();
  $("#evaluation-table tbody").replaceChildren();
  try {
    const report = await api("/v1/evaluation");
    showInlineError("#evaluation-error", "");
    const labels = {
      route_accuracy: "路由正确率",
      retrieval_recall_at_3: "Recall@3",
      citation_accuracy: "引用正确率",
      refusal_accuracy: "拒答正确率",
      permission_isolation: "权限隔离",
      tool_answer_accuracy: "工具答案",
    };
    Object.entries(labels).forEach(([key, label]) => {
      const item = document.createElement("div");
      item.className = "metric-item";
      const name = document.createElement("span");
      name.textContent = label;
      const value = document.createElement("b");
      value.textContent = percent(report.metrics[key]);
      value.className = report.checks[key] ? "is-pass" : "is-fail";
      item.append(name, value);
      strip.append(item);
    });
    const table = $("#evaluation-table tbody");
    Object.entries(report.by_category).forEach(([category, metrics]) => {
      const row = document.createElement("tr");
      [category, metrics.count, percent(metrics.route_accuracy), percent(metrics.evidence_recall), percent(metrics.refusal_accuracy)].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      table.append(row);
    });
  } catch (error) {
    showInlineError("#evaluation-error", `加载失败：${error.message}`);
  }
}

async function loadAudit() {
  const body = $("#audit-table tbody");
  body.replaceChildren();
  try {
    const events = await api("/v1/audit?limit=100");
    showInlineError("#audit-error", "");
    for (const event of events) {
      const row = document.createElement("tr");
      [new Date(event.timestamp).toLocaleString(), routeLabels[event.route] || event.route, event.allowed ? "允许" : "拒绝", event.source_ids.join(", ") || "-", event.trace_id].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      body.append(row);
    }
  } catch (error) {
    showInlineError("#audit-error", `加载失败：${error.message}`);
  }
}

async function switchView(view) {
  state.view = view;
  $$(".nav-button").forEach((button) => button.classList.toggle("is-active", button.dataset.view === view));
  $$(".view").forEach((panel) => {
    const active = panel.id === `view-${view}`;
    panel.hidden = !active;
    panel.classList.toggle("is-active", active);
  });
  $("#view-eyebrow").textContent = viewMeta[view][0];
  $("#view-title").textContent = viewMeta[view][1];
  if (view === "knowledge") await loadKnowledge();
  if (view === "evaluation") await loadEvaluation();
  if (view === "audit") await loadAudit();
  $("#main-content").focus({ preventScroll: true });
}

async function changeRole(role) {
  state.role = role;
  localStorage.setItem("rag-role", role);
  state.token = null;
  await issueToken();
  await loadSamples();
  if (state.view !== "query") await switchView(state.view);
  showToast(`身份已切换为 ${role}`);
}

async function init() {
  $("#role-select").value = state.role;
  await refreshHealth();
  try {
    await issueToken();
    await loadSamples();
  } catch (error) {
    showToast(`身份初始化失败：${error.message}`);
  }
  $("#query-form").addEventListener("submit", submitQuery);
  $("#ingest-form").addEventListener("submit", submitIngest);
  $("#role-select").addEventListener("change", (event) => changeRole(event.target.value));
  $$(".nav-button").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  $$(".feedback-actions button").forEach((button) => button.addEventListener("click", () => submitFeedback(button.dataset.rating)));
  if (window.lucide) window.lucide.createIcons({ attrs: { "aria-hidden": "true" } });
}

init();
