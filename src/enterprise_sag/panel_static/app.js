(function () {
  "use strict";

  const form = document.getElementById("search-form");
  const queryInput = document.getElementById("query");
  const submitButton = document.getElementById("submit-button");
  const emptyState = document.getElementById("empty-state");
  const loadingState = document.getElementById("loading-state");
  const errorState = document.getElementById("error-state");
  const results = document.getElementById("results");
  const loadingMessage = document.getElementById("loading-message");
  const ingestionForm = document.getElementById("ingestion-form");
  const ingestionButton = document.getElementById("ingestion-submit");
  const ingestionFeedback = document.getElementById("ingestion-feedback");
  const sourceFile = document.getElementById("source-file");
  let loadingTimer = null;

  const displayText = {
    status: {
      covered: "已覆盖",
      uncovered: "未覆盖",
    },
    timeMode: {
      any: "任意时间",
      historical: "历史信息",
      latest_valid: "当前有效",
    },
    reason: {
      "selected-evidence": "已有证据入选",
      "no-validated-evidence": "没有通过判定的证据",
      "token-budget-exceeded": "超出令牌预算",
      "no-coverage-record": "没有覆盖记录",
    },
    planner: {
      "deepseek-evidence-need-planner-v1": "DeepSeek 证据需求规划器 v1",
      "single-need-fallback-v1": "本地单需求规划器 v1",
    },
    supportReason: {
      "relative-route-head": "本地相对得分达到支持阈值",
      "unjudged-direct-fusion": "未经大模型判定，按直接检索结果融合",
      "semantic-support": "语义上直接支持该证据需求",
    },
  };

  function localize(group, value) {
    return displayText[group]?.[value] || value || "—";
  }

  function element(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined && value !== null) node.textContent = String(value);
    return node;
  }

  function formatNumber(value, digits = 0) {
    const number = Number(value);
    return Number.isFinite(number)
      ? new Intl.NumberFormat("zh-CN", { maximumFractionDigits: digits }).format(number)
      : "—";
  }

  function parseList(value) {
    return [...new Set(value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean))];
  }

  function showState(name) {
    emptyState.hidden = name !== "empty";
    loadingState.hidden = name !== "loading";
    errorState.hidden = name !== "error";
    results.hidden = name !== "results";
  }

  function startLoadingMessages() {
    const messages = [
      "规划证据需求（EvidenceNeed），随后运行多路 SAG 检索……",
      "计算事件、证据和实体种子，并执行 SQL 局部扩展……",
      "判定候选事件是否直接支持各项证据需求……",
      "进行覆盖融合、去重和令牌（Token）编排……",
    ];
    let index = 0;
    loadingMessage.textContent = messages[index];
    loadingTimer = window.setInterval(() => {
      index = Math.min(index + 1, messages.length - 1);
      loadingMessage.textContent = messages[index];
    }, 6500);
  }

  function stopLoadingMessages() {
    if (loadingTimer !== null) {
      window.clearInterval(loadingTimer);
      loadingTimer = null;
    }
  }

  async function loadStatus() {
    const runtimeDot = document.getElementById("runtime-dot");
    try {
      const response = await fetch("/api/status", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("本地索引不可用");
      const data = await response.json();
      document.getElementById("runtime-title").textContent = "本地索引已就绪";
      document.getElementById("runtime-index").textContent = data.index_version || "—";
      document.getElementById("runtime-index").title = data.index_version || "";
      document.getElementById("runtime-events").textContent = formatNumber(data.stats?.events);
      document.getElementById("runtime-entities").textContent = formatNumber(data.stats?.entities);
      document.getElementById("runtime-integrity").textContent =
        data.integrity_check === "ok" ? "正常" : (data.integrity_check || "—");
      runtimeDot.classList.remove("is-error");
    } catch (_error) {
      document.getElementById("runtime-title").textContent = "无法读取本地索引";
      document.getElementById("runtime-integrity").textContent = "错误";
      runtimeDot.classList.add("is-error");
    }
  }

  function selectSourceForUpdate(source) {
    const card = document.getElementById("ingestion-card");
    card.open = true;
    document.getElementById("source-asset-id").value = source.asset_id || "";
    document.getElementById("source-key").value = source.source_key || "";
    document.getElementById("source-namespace").value = source.namespace || "enterprise_knowledge";
    document.getElementById("source-title").value = source.title || "";
    document.getElementById("source-metadata").value = JSON.stringify(source.metadata || {}, null, 2);
    ingestionFeedback.className = "ingestion-feedback";
    ingestionFeedback.textContent = `已选择“${source.title}”。选择新文件后会生成版本 ${Number(source.version_number) + 1}。`;
    sourceFile.focus();
  }

  function renderSources(sources) {
    const container = document.getElementById("source-list");
    container.replaceChildren();
    if (!sources.length) {
      container.append(element("p", "source-list-empty", "还没有可用资料。上传后会显示在这里。"));
      return;
    }
    for (const source of sources.slice(0, 8)) {
      const item = element("article", "source-item");
      const header = element("header");
      const update = element("button", "text-button", "更新此资料");
      update.type = "button";
      update.addEventListener("click", () => selectSourceForUpdate(source));
      header.append(element("strong", "", source.title), update);
      item.append(
        header,
        element("p", "", `${source.namespace} · 版本 ${source.version_number} · ${source.evidence_units} 个证据块`),
        element("p", "", source.asset_id),
      );
      container.append(item);
    }
  }

  async function loadSources() {
    const container = document.getElementById("source-list");
    try {
      const response = await fetch("/api/sources", { headers: { Accept: "application/json" } });
      const data = await response.json();
      if (!response.ok) throw new Error(errorDetail(data, response.status));
      renderSources(data);
    } catch (error) {
      container.replaceChildren(
        element("p", "source-list-empty", error.message || "无法读取资料列表。"),
      );
    }
  }

  function summaryCard(label, value, note) {
    const card = element("dl", "summary-card");
    card.append(element("dt", "", label), element("dd", "", value));
    if (note) card.append(element("small", "", note));
    return card;
  }

  function renderSummary(pack, diagnostics) {
    const container = document.getElementById("result-summary");
    container.replaceChildren();
    const covered = pack.coverage.filter((item) => item.status === "covered").length;
    const candidateCounts = Object.values(diagnostics.route_candidates || {});
    const candidateTotal = candidateCounts.reduce((total, value) => total + Number(value || 0), 0);
    container.append(
      summaryCard(
        "证据需求",
        formatNumber(pack.plan.needs.length),
        `规划器：${localize("planner", pack.plan.planner)}`,
      ),
      summaryCard("覆盖情况", `${covered} / ${pack.coverage.length}`, "已覆盖 / 总需求"),
      summaryCard("候选数量", formatNumber(candidateTotal), `${candidateCounts.length} 条需求路径`),
      summaryCard("证据块", formatNumber(pack.items.length), `${pack.excluded_items.length} 个未纳入`),
      summaryCard(
        "令牌预算",
        `${formatNumber(pack.estimated_tokens)} / ${formatNumber(pack.maximum_tokens)}`,
        "估算用量 / 上限",
      ),
      summaryCard(
        "检索耗时",
        `${formatNumber(diagnostics.elapsed_seconds, 2)} 秒`,
        `${diagnostics.llm_requests} 次大模型请求`,
      ),
    );
  }

  function renderNeeds(pack) {
    const container = document.getElementById("needs-grid");
    const coverageById = new Map(pack.coverage.map((item) => [item.need_id, item]));
    container.replaceChildren();
    for (const [needIndex, need] of pack.plan.needs.entries()) {
      const coverage = coverageById.get(need.need_id);
      const status = coverage?.status || "uncovered";
      const card = element("article", `need-card is-${status}`);
      const header = element("header");
      header.append(
        element("h4", "", `证据需求 ${needIndex + 1}`),
        element("span", `state-pill is-${status}`, localize("status", status)),
      );
      const meta = element("div", "need-meta");
      meta.append(
        element("span", "metric-chip", need.required ? "必需" : "可选"),
        element("span", "metric-chip", `权重 ${need.weight}`),
        element("span", "metric-chip", localize("timeMode", need.time_mode)),
      );
      for (const facet of need.facets || []) meta.append(element("span", "metric-chip", facet));
      card.append(
        header,
        element("p", "technical-id", `标识：${need.need_id}`),
        element("p", "", need.description),
        meta,
        element("p", "need-query", need.query),
        element("p", "need-query", localize("reason", coverage?.reason || "no-coverage-record")),
      );
      container.append(card);
    }
    document.getElementById("planner-label").textContent =
      `规划器：${localize("planner", pack.plan.planner)}`;
  }

  function pathItem(label, value) {
    const item = element("div", "path-item");
    const code = element("code", "", value || "—");
    code.title = value || "";
    item.append(element("span", "", label), code);
    return item;
  }

  function traceCard(trace) {
    const card = element("article", "trace-card");
    const header = element("header");
    header.append(
      element("strong", "", `需求标识：${trace.need_id}`),
      element(
        "span",
        "state-pill is-covered",
        `支持度 ${formatNumber(trace.semantic_support_score, 2)}`,
      ),
    );
    const metrics = element("div", "trace-metrics");
    const retrieval = trace.retrieval_trace || {};
    const values = [
      ["路径排名", trace.route_rank],
      ["路径得分", formatNumber(trace.route_score, 3)],
      ["事件向量", formatNumber(retrieval.direct_event_score, 3)],
      ["证据向量", formatNumber(retrieval.direct_evidence_score, 3)],
      ["实体向量", formatNumber(retrieval.entity_score, 3)],
      ["全文检索", formatNumber(retrieval.lexical_score, 3)],
      ["SQL 跳数", retrieval.expansion_hop],
    ];
    for (const [label, value] of values) {
      metrics.append(element("span", "metric-chip", `${label} ${value}`));
    }
    if (retrieval.shared_entities?.length) {
      metrics.append(
        element("span", "metric-chip", `共现实体 ${retrieval.shared_entities.join(", ")}`),
      );
    }
    card.append(
      header,
      element(
        "p",
        "trace-reason",
        localize("supportReason", trace.semantic_support_reason),
      ),
      metrics,
    );
    return card;
  }

  function evidenceCard(item, index) {
    const details = element("details", "evidence-card");
    if (index === 0) details.open = true;
    const summary = element("summary", "evidence-summary");
    const identity = element("div");
    const titleRow = element("div", "evidence-title-row");
    titleRow.append(element("h4", "", item.title));
    for (const needId of item.matched_need_ids) {
      titleRow.append(element("span", "need-chip", needId));
    }
    identity.append(titleRow, element("p", "evidence-event", item.event_summary));
    summary.append(
      element("span", "evidence-index", String(index + 1).padStart(2, "0")),
      identity,
      element("span", "evidence-score", formatNumber(item.score, 3)),
    );

    const content = element("div", "evidence-content");
    const provenance = element("section");
    provenance.append(element("h5", "", "来源定位（Provenance）"));
    const paths = element("div", "path-grid");
    paths.append(
      pathItem("来源文件", item.source_path),
      pathItem("章节路径", (item.section_path || []).join(" > ") || "（根节点）"),
      pathItem("原文锚点", (item.anchors || []).join(", ") || "（无）"),
      pathItem("事件与证据标识", `${item.event_id} · ${item.evidence_id}`),
    );
    provenance.append(paths);

    const traces = element("section");
    traces.append(element("h5", "", "检索路径明细（Route Trace）"));
    const traceList = element("div", "trace-list");
    for (const trace of item.route_traces || []) traceList.append(traceCard(trace));
    traces.append(traceList);

    const raw = element("section");
    raw.append(
      element("h5", "", `原始证据 · 约 ${formatNumber(item.estimated_tokens)} 个令牌`),
      element("pre", "raw-evidence", item.content),
    );
    content.append(provenance, traces, raw);
    details.append(summary, content);
    return details;
  }

  function renderBlocks(pack) {
    const container = document.getElementById("blocks-list");
    container.replaceChildren();
    if (!pack.items.length) {
      const empty = element("section", "state-card empty-state");
      empty.append(element("h3", "", "没有通过支持判定的证据块"));
      empty.append(
        element(
          "p",
          "",
          "查看上方未覆盖的证据需求；系统不会为了填满结果而加入低相关内容。",
        ),
      );
      container.append(empty);
    } else {
      pack.items.forEach((item, index) => container.append(evidenceCard(item, index)));
    }
    document.getElementById("block-count").textContent =
      `已选 ${pack.items.length} 个 / 未纳入 ${pack.excluded_items.length} 个`;
  }

  function renderExcluded(pack) {
    const section = document.getElementById("excluded-section");
    const list = document.getElementById("excluded-list");
    list.replaceChildren();
    section.hidden = !pack.excluded_items.length;
    for (const item of pack.excluded_items) {
      list.append(element("li", "", `${item.event_id} · ${localize("reason", item.reason)}`));
    }
  }

  function renderResults(data) {
    const pack = data.pack;
    renderSummary(pack, data.diagnostics);
    renderNeeds(pack);
    renderBlocks(pack);
    renderExcluded(pack);
    showState("results");
    document.getElementById("main-content").focus({ preventScroll: true });
  }

  function errorDetail(data, status) {
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) {
      return data.detail.map((item) => item.msg || "参数无效").join("；");
    }
    return `HTTP ${status}`;
  }

  async function submitIngestion(event) {
    event.preventDefault();
    if (!sourceFile.files?.length) {
      sourceFile.focus();
      return;
    }
    let metadata;
    try {
      metadata = JSON.parse(document.getElementById("source-metadata").value || "{}");
      if (!metadata || Array.isArray(metadata) || typeof metadata !== "object") {
        throw new Error("扩展元数据必须是 JSON 对象。例：{\"department\":\"content\"}");
      }
    } catch (error) {
      ingestionFeedback.className = "ingestion-feedback is-error";
      ingestionFeedback.textContent = error.message || "扩展元数据不是有效 JSON。";
      document.getElementById("source-metadata").focus();
      return;
    }

    const formData = new FormData();
    formData.append("file", sourceFile.files[0]);
    const fields = [
      ["asset_id", "source-asset-id"],
      ["source_key", "source-key"],
      ["namespace", "source-namespace"],
      ["title", "source-title"],
    ];
    for (const [name, id] of fields) {
      const value = document.getElementById(id).value.trim();
      if (value) formData.append(name, value);
    }
    formData.append("metadata_json", JSON.stringify(metadata));

    ingestionButton.disabled = true;
    ingestionButton.querySelector("span").textContent = "解析、抽取并建立索引中";
    ingestionFeedback.className = "ingestion-feedback";
    ingestionFeedback.textContent = "正在生成证据块、事件、实体与向量；当前检索索引会在全部成功后一次切换。";
    try {
      const response = await fetch("/api/ingestions/upload", {
        method: "POST",
        headers: { Accept: "application/json" },
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(errorDetail(data, response.status));
      const unchanged = data.status === "unchanged";
      ingestionFeedback.className = "ingestion-feedback is-success";
      ingestionFeedback.textContent = unchanged
        ? `内容与当前版本相同，未重复抽取。资料版本仍为 ${data.version_number}。`
        : `接入完成：版本 ${data.version_number}，新增 ${data.evidence_units} 个证据块；索引已原子切换。`;
      document.getElementById("source-asset-id").value = data.asset_id;
      document.getElementById("source-file-name").textContent = "请选择下一份文件";
      sourceFile.value = "";
      await Promise.all([loadStatus(), loadSources()]);
    } catch (error) {
      ingestionFeedback.className = "ingestion-feedback is-error";
      ingestionFeedback.textContent = `${error.message || "资料接入失败"} 请检查文件、模型配置后重试；当前索引没有改变。`;
    } finally {
      ingestionButton.disabled = false;
      ingestionButton.querySelector("span").textContent = "增量接入资料";
    }
  }

  async function submitSearch(event) {
    event.preventDefault();
    const query = queryInput.value.trim();
    if (!query) {
      queryInput.focus();
      return;
    }
    submitButton.disabled = true;
    submitButton.querySelector("span").textContent = "检索中";
    showState("loading");
    startLoadingMessages();
    const payload = {
      query,
      purpose: document.getElementById("purpose").value.trim() || "evidence_review",
      top_k: Number(document.getElementById("top-k").value),
      maximum_tokens: Number(document.getElementById("maximum-tokens").value),
      use_deepseek: document.getElementById("use-deepseek").checked,
      subject_refs: parseList(document.getElementById("subject-refs").value),
      namespaces: parseList(document.getElementById("namespaces").value),
    };
    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(errorDetail(data, response.status));
      renderResults(data);
      loadStatus();
    } catch (error) {
      document.getElementById("error-message").textContent = error.message || "未知错误";
      showState("error");
    } finally {
      stopLoadingMessages();
      submitButton.disabled = false;
      submitButton.querySelector("span").textContent = "运行检索";
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (window.lucide) window.lucide.createIcons();
    loadStatus();
    loadSources();
  });

  queryInput.addEventListener("input", () => {
    document.getElementById("query-count").textContent = String(queryInput.value.length);
  });
  form.addEventListener("submit", submitSearch);
  ingestionForm.addEventListener("submit", submitIngestion);
  sourceFile.addEventListener("change", () => {
    document.getElementById("source-file-name").textContent =
      sourceFile.files?.[0]?.name || "DOCX、PDF、PPTX、XLSX、HTML、Markdown 或 TXT";
  });
  document.getElementById("refresh-sources").addEventListener("click", loadSources);
  document.getElementById("retry-button").addEventListener("click", () => form.requestSubmit());
  document.querySelectorAll("[data-sample]").forEach((button) => {
    button.addEventListener("click", () => {
      queryInput.value = button.dataset.sample || "";
      document.getElementById("purpose").value = button.dataset.purpose || "evidence_review";
      document.getElementById("query-count").textContent = String(queryInput.value.length);
      queryInput.focus();
    });
  });
})();
