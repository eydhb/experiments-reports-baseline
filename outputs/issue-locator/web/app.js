"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { source: "sample", repository: null, busy: false, result: null, modelAvailable: false };
  const importLabels = { sample: "导入示例仓库", local: "导入本地仓库", github: "导入 GitHub 仓库" };

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function feedback(id, message, kind = "") {
    const node = $(id);
    node.textContent = message;
    node.className = ["feedback", kind].filter(Boolean).join(" ");
    node.hidden = !message;
  }

  function setBusy(busy) {
    state.busy = busy;
    document.querySelectorAll(".source-tab").forEach((button) => { button.disabled = busy; });
    ["import-button", "repo-path", "repo-url", "mode", "refresh-status"].forEach((id) => { $(id).disabled = busy; });
    $("analyze-button").disabled = busy || !state.repository;
    $("analyze-button").replaceChildren(el("span", "", busy ? "处理中…" : "开始定位"), el("span", "", "→"));
  }

  async function api(path, body) {
    const options = body === undefined
      ? { headers: { Accept: "application/json" } }
      : { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(body) };
    let response;
    try {
      response = await fetch(path, options);
    } catch (_) {
      throw new Error("无法连接本地服务，请确认启动窗口仍在运行，然后重试。");
    }
    let data;
    try {
      data = await response.json();
    } catch (_) {
      throw new Error(`服务返回了无法读取的响应（HTTP ${response.status}）。`);
    }
    if (!response.ok || data.error) throw new Error(data.error || `请求失败（HTTP ${response.status}）。`);
    return data;
  }

  function updateModeNote() {
    $("mode-note").textContent = $("mode").value === "model"
      ? "模型模式会将问题与所需代码片段发送至已配置的模型服务，请确认仓库内容适合发送。"
      : "规则模式使用本地关键词与符号关联检索，不向模型服务发送代码。";
  }

  async function refreshStatus() {
    $("refresh-status").disabled = true;
    try {
      const status = await api("/api/status");
      state.modelAvailable = Boolean(status.model_available);
      $("service-status").textContent = `${status.engine || "本地服务"} 已连接`;
      $("service-dot").className = "status-dot ready";
      const modelOption = $("mode").querySelector('option[value="model"]');
      modelOption.disabled = !state.modelAvailable;
      modelOption.textContent = state.modelAvailable ? "模型 Agent" : "模型 Agent（未配置）";
      modelOption.title = status.model || "";
      if (!state.modelAvailable) $("mode").value = "offline";
      updateModeNote();
    } catch (error) {
      $("service-status").textContent = "本地服务未连接";
      $("service-dot").className = "status-dot failed";
      $("service-status").title = error.message;
    } finally {
      $("refresh-status").disabled = state.busy;
    }
  }

  function setSource(source) {
    state.source = source;
    document.querySelectorAll(".source-tab").forEach((button) => {
      const active = button.dataset.source === source;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    ["sample", "local", "github"].forEach((name) => { $(`source-${name}`).hidden = name !== source; });
    $("import-button").replaceChildren(document.createTextNode(importLabels[source] + " "), el("span", "", "↗"));
    feedback("import-message", "");
    if (source === "local") $("repo-path").focus();
    if (source === "github") $("repo-url").focus();
  }

  function clearResults() {
    state.result = null;
    $("result-content").hidden = true;
    $("empty-state").hidden = false;
    $("result-count").hidden = true;
    $("export-button").hidden = true;
    feedback("analyze-message", "");
  }

  function renderRepository(repo) {
    state.repository = repo;
    $("repository-name").textContent = repo.name;
    $("repository-name").title = repo.name;
    $("repository-path").textContent = repo.path;
    $("repository-path").title = repo.path;
    $("repository-count").textContent = repo.file_count.toLocaleString();
    $("repository-files").replaceChildren(...(repo.files || []).map((path) => el("li", "", path)));
    $("files-truncated").hidden = !repo.truncated;
    $("repository-details").hidden = false;
    clearResults();
  }

  async function importRepository(event) {
    if (event) event.preventDefault();
    if (state.busy) return;
    const payload = { source: state.source };
    if (state.source === "local") {
      payload.path = $("repo-path").value.trim();
      if (!payload.path) return feedback("import-message", "请填写本地仓库的完整路径。", "error");
    }
    if (state.source === "github") {
      payload.url = $("repo-url").value.trim();
      if (!payload.url) return feedback("import-message", "请填写公开 GitHub 仓库地址。", "error");
    }
    setBusy(true);
    $("import-button").textContent = "正在导入…";
    feedback("import-message", state.source === "github" ? "正在获取仓库，耗时取决于项目大小与网络连接。" : "正在读取仓库文件列表…", "loading");
    try {
      const data = await api("/api/import", payload);
      renderRepository(data.repository);
      feedback("import-message", `仓库已就绪，可以开始定位。`);
    } catch (error) {
      feedback("import-message", error.message, "error");
    } finally {
      $("import-button").replaceChildren(document.createTextNode(importLabels[state.source] + " "), el("span", "", "↗"));
      setBusy(false);
    }
  }

  function renderTrace(trace) {
    $("trace-count").textContent = `· ${trace.length} 次`;
    $("trace-list").replaceChildren();
    if (!trace.length) {
      $("trace-list").append(el("li", "trace-description", "本次响应未返回工具调用记录。"));
      return;
    }
    for (const item of trace) {
      const li = el("li", "trace-item");
      li.append(el("div", "trace-tool", item.tool || "tool"));
      if (item.args !== undefined) li.append(el("div", "trace-args", typeof item.args === "string" ? item.args : JSON.stringify(item.args)));
      const pieces = [];
      if (item.summary) pieces.push(item.summary);
      if (typeof item.result_count === "number") pieces.push(`${item.result_count} 条结果`);
      if (pieces.length) li.append(el("div", "trace-description", pieces.join(" · ")));
      $("trace-list").append(li);
    }
  }

  function codeBlock(lines) {
    const block = el("div", "code-block");
    block.setAttribute("role", "region");
    block.setAttribute("aria-label", "带行号的源代码");
    block.tabIndex = 0;
    for (const item of lines) {
      const row = el("div", "code-row");
      row.append(el("span", "line-number", item.line), el("code", "code-text", item.text));
      block.append(row);
    }
    return block;
  }

  function stringList(items) {
    const ul = el("ul");
    items.forEach((item) => ul.append(el("li", "", item)));
    return ul;
  }

  function renderCandidate(candidate, index, repositoryId) {
    const card = el("article", "panel candidate");
    const header = el("div", "candidate-header");
    const title = el("div", "candidate-title");
    title.append(el("h3", "", candidate.path), el("span", "line-label", `L${candidate.start_line}–${candidate.end_line}`));
    header.append(el("span", "rank", String(index + 1).padStart(2, "0")), title);
    const body = el("div", "candidate-body");
    body.append(el("p", "candidate-reason", candidate.reason));
    if (candidate.evidence && candidate.evidence.length) {
      body.append(el("span", "evidence-label", "代码依据"), codeBlock(candidate.evidence));
    }
    const readButton = el("button", "text-button read-context", "读取更多上下文 ↗");
    readButton.type = "button";
    readButton.setAttribute("aria-expanded", "false");
    const context = el("div", "context-container");
    context.hidden = true;
    let contextLoaded = false;
    readButton.addEventListener("click", async () => {
      if (contextLoaded) {
        context.hidden = !context.hidden;
        readButton.setAttribute("aria-expanded", String(!context.hidden));
        readButton.textContent = context.hidden ? "展开文件上下文 ↗" : "收起文件上下文 ↑";
        return;
      }
      readButton.disabled = true;
      readButton.textContent = "正在读取文件…";
      try {
        const start = Math.max(1, Number(candidate.start_line) - 10);
        const end = Math.max(start, Number(candidate.end_line) + 15);
        const query = new URLSearchParams({ repository_id: repositoryId, path: candidate.path, start_line: start, end_line: end });
        const file = await api(`/api/file?${query.toString()}`);
        context.replaceChildren(el("p", "context-caption", `已读取 ${file.path} · L${file.start_line}–${file.end_line}`), codeBlock(file.lines || []));
        context.hidden = false;
        contextLoaded = true;
        readButton.setAttribute("aria-expanded", "true");
        readButton.textContent = "收起文件上下文 ↑";
      } catch (error) {
        context.replaceChildren(el("p", "feedback error", error.message));
        context.hidden = false;
        readButton.textContent = "重新读取上下文 ↗";
      } finally {
        readButton.disabled = false;
      }
    });
    body.append(readButton, context);
    if (candidate.pending && candidate.pending.length) {
      const pending = el("div", "candidate-pending");
      pending.append(el("h4", "", "待验证"), stringList(candidate.pending));
      body.append(pending);
    }
    card.append(header, body);
    return card;
  }

  function renderResults(data, repositoryId) {
    state.result = data;
    const candidates = data.candidates || [];
    $("result-count").textContent = candidates.length;
    $("result-count").hidden = false;
    $("result-mode").textContent = data.mode === "model" ? "模型 Agent · 基于代码证据" : "规则检索演示 · 未调用模型";
    const timing = Number(data.elapsed_ms);
    $("result-timing").textContent = [data.engine, Number.isFinite(timing) ? `${(timing / 1000).toFixed(2)} s` : ""].filter(Boolean).join(" · ");
    $("result-summary").textContent = data.summary || "以下为根据代码搜索与阅读得到的候选位置。";
    const warnings = data.warnings || [];
    $("result-warnings").replaceChildren(...warnings.map((message) => el("p", "", message)));
    $("result-warnings").hidden = !warnings.length;
    renderTrace(data.trace || []);
    $("candidates").replaceChildren(...candidates.map((candidate, index) => renderCandidate(candidate, index, repositoryId)));
    if (!candidates.length) $("candidates").append(el("div", "no-candidates", "未找到足够相关的候选文件。补充接口路径、异常类型或堆栈后再试。"));
    $("pending-list").replaceChildren(...(data.pending || []).map((item) => el("li", "", item)));
    $("global-pending").hidden = !(data.pending || []).length;
    $("empty-state").hidden = true;
    $("result-content").hidden = false;
    $("export-button").hidden = false;
    $("results-heading").focus({ preventScroll: true });
  }

  async function analyze(event) {
    if (event) event.preventDefault();
    if (state.busy) return;
    if (!state.repository) return feedback("analyze-message", "请先导入一个仓库。", "error");
    const issue = $("issue").value.trim();
    if (!issue) {
      feedback("analyze-message", "请先描述你遇到的问题。", "error");
      $("issue").focus();
      return;
    }
    const mode = $("mode").value;
    if (mode === "model" && !state.modelAvailable) return feedback("analyze-message", "模型服务尚未配置，请使用规则检索演示或配置模型后刷新服务状态。", "error");
    const repositoryId = state.repository.id;
    setBusy(true);
    feedback("analyze-message", "");
    $("empty-state").hidden = true;
    $("result-content").hidden = true;
    $("export-button").hidden = true;
    $("result-count").hidden = true;
    $("loading-state").hidden = false;
    $("loading-description").textContent = mode === "model" ? "模型正在选择工具并读取代码。完成后将展示实际调用记录，耗时取决于模型服务。" : "正在执行本地搜索与代码阅读，完成后将展示实际工具记录。";
    document.querySelector(".results-section").setAttribute("aria-busy", "true");
    try {
      const data = await api("/api/analyze", { repository_id: repositoryId, issue, mode });
      renderResults(data, repositoryId);
    } catch (error) {
      state.result = null;
      feedback("analyze-message", error.message, "error");
      $("empty-state").hidden = false;
    } finally {
      $("loading-state").hidden = true;
      document.querySelector(".results-section").setAttribute("aria-busy", "false");
      setBusy(false);
    }
  }

  function exportResult() {
    if (!state.result) return;
    const artifact = { repository: { name: state.repository.name, source: state.repository.source, file_count: state.repository.file_count }, ...state.result };
    const blob = new Blob([JSON.stringify(artifact, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = el("a");
    anchor.href = url;
    anchor.download = `codelens-${String(state.repository.name).replace(/[^\w.-]/g, "_")}-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  document.querySelectorAll(".source-tab").forEach((button) => button.addEventListener("click", () => setSource(button.dataset.source)));
  $("import-form").addEventListener("submit", importRepository);
  $("analyze-form").addEventListener("submit", analyze);
  $("mode").addEventListener("change", updateModeNote);
  $("export-button").addEventListener("click", exportResult);
  $("refresh-status").addEventListener("click", refreshStatus);
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      analyze();
    }
  });
  Promise.allSettled([refreshStatus(), importRepository()]);
})();
