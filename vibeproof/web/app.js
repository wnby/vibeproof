// VibeProof Web 工作台的浏览器控制器：调用接管 API，并渲染活动、证据、学习计划与运行报告。
const state = {
  run: null,
  report: null,
  relativePath: "",
  activeTab: "overview",
  recentRuns: [],
  serverConfig: null,
  runStartedAt: null,
  elapsedTimer: null,
  pollTimer: null,
};

const elements = {
  form: document.querySelector("#takeover-form"),
  welcome: document.querySelector("#welcome-view"),
  runView: document.querySelector("#run-view"),
  resultSection: document.querySelector("#result-section"),
  resultContent: document.querySelector("#result-content"),
  activityFeed: document.querySelector("#activity-feed"),
  activitySummary: document.querySelector("#activity-summary"),
  taskPrompt: document.querySelector("#task-prompt"),
  repositoryTitle: document.querySelector("#repository-title"),
  runState: document.querySelector("#run-state"),
  runStateLabel: document.querySelector("#run-state-label"),
  startButton: document.querySelector("#start-button"),
  recentRuns: document.querySelector("#recent-runs"),
  provider: document.querySelector("#provider"),
  model: document.querySelector("#model"),
  analysisDepth: document.querySelector("#analysis-depth"),
  repositoryPath: document.querySelector("#repository-path"),
  runtimeMode: document.querySelector("#runtime-mode"),
  sidebarProvider: document.querySelector("#sidebar-provider"),
  inspector: document.querySelector("#inspector"),
  inspectorTitle: document.querySelector("#inspector-title"),
  inspectorBody: document.querySelector("#inspector-body"),
  toast: document.querySelector("#toast"),
  serverConfig: document.querySelector("#server-config"),
  serverConfigTitle: document.querySelector("#server-config-title"),
  serverConfigDetail: document.querySelector("#server-config-detail"),
};

elements.form.addEventListener("submit", startTakeover);
document.querySelector("#new-task").addEventListener("click", resetWorkspace);
document.querySelector("#close-inspector").addEventListener("click", () => elements.inspector.classList.add("closed"));
document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => selectTab(button.dataset.tab));
});
elements.provider.addEventListener("change", updateProviderLabel);
elements.recentRuns.addEventListener("click", openRecentRun);
elements.resultContent.addEventListener("click", handleResultAction);

updateProviderLabel();
loadServerConfiguration();
loadRecentRuns();

async function loadServerConfiguration() {
  try {
    const response = await fetch("/api/v1/config");
    const config = await parseResponse(response);
    if (!response.ok) throw new Error(config.detail || "无法读取服务端配置");
    state.serverConfig = config;
    if ([...elements.provider.options].some((option) => option.value === config.provider)) {
      elements.provider.value = config.provider;
    }
    if (config.model) elements.model.value = config.model;
    elements.analysisDepth.value = config.defaultAnalysisDepth || "deep";
    renderServerConfiguration(config);
    updateProviderLabel();
  } catch (error) {
    elements.serverConfig.className = "server-config unavailable";
    elements.serverConfigTitle.textContent = "服务端配置不可用";
    elements.serverConfigDetail.textContent = error.message;
  }
}

function renderServerConfiguration(config) {
  const realProvider = config.provider !== "mock";
  const modelReady = realProvider && config.endpointConfigured && config.apiKeyConfigured && config.model;
  const ready = config.workspaceConfigured && (!realProvider || modelReady);
  elements.serverConfig.className = `server-config ${ready ? "ready" : "unavailable"}`;
  elements.serverConfigTitle.textContent = ready ? "服务端已准备好" : "服务端还缺少配置";
  const workspace = config.workspaceName ? `工作区 ${config.workspaceName}` : "未配置工作区";
  const model = realProvider ? `${config.model || "未指定模型"} · ${config.apiKeyConfigured ? "密钥已配置" : "缺少密钥"}` : "Mock · 确定性";
  elements.serverConfigDetail.textContent = `${workspace}；${model}`;
}

async function startTakeover(event) {
  event.preventDefault();
  const relativePath = elements.repositoryPath.value.trim();
  if (!relativePath) return;

  state.relativePath = relativePath;
  state.run = null;
  state.report = null;
  elements.welcome.classList.add("hidden");
  elements.runView.classList.remove("hidden");
  elements.resultSection.classList.add("hidden");
  elements.repositoryTitle.textContent = leafName(relativePath);
  elements.taskPrompt.innerHTML = `接管 <code>${escapeHtml(relativePath)}</code>，生成有源码依据的架构、学习路径和运行证据。`;
  elements.activityFeed.innerHTML = runningActivity("正在创建后台任务");
  elements.activitySummary.textContent = "处理中";
  elements.startButton.disabled = true;
  startElapsedTimer();
  setRunState("running", "运行中");

  const payload = {
    relativePath,
    provider: elements.provider.value,
    analysisDepth: elements.analysisDepth.value,
    executeRuntime: elements.runtimeMode.value !== "plan",
    runtimeCheck: elements.runtimeMode.value === "collect" ? "pytest-collect" : "pytest",
  };
  const model = elements.model.value.trim();
  if (model) payload.model = model;

  try {
    const response = await fetch("/api/v1/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await parseResponse(response);
    if (!response.ok) throw new Error(body.detail || `请求失败，HTTP ${response.status}`);
    applyRun(body);
    await pollRun(body.run_id);
  } catch (error) {
    renderRequestFailure(error);
  }
}

async function pollRun(runId) {
  clearTimeout(state.pollTimer);
  try {
    const response = await fetch(`/api/v1/runs/${encodeURIComponent(runId)}`);
    const body = await parseResponse(response);
    if (!response.ok) throw new Error(body.detail || "无法读取任务状态");
    applyRun(body);
    if (["PENDING", "RUNNING"].includes(body.status)) {
      state.pollTimer = setTimeout(() => pollRun(runId), 900);
      return;
    }
    finishRun();
  } catch (error) {
    finishRun();
    renderRequestFailure(error);
  }
}

function applyRun(run) {
  state.run = run;
  state.report = run.report;
  state.relativePath = run.configuration.relative_path;
  elements.welcome.classList.add("hidden");
  elements.runView.classList.remove("hidden");
  elements.repositoryTitle.textContent = run.report?.repository_name || leafName(state.relativePath);
  elements.taskPrompt.innerHTML = `接管 <code>${escapeHtml(state.relativePath)}</code>，Run <code>${escapeHtml(run.run_id)}</code>`;
  renderRunActivity();
  if (run.report) {
    elements.resultSection.classList.remove("hidden");
    selectTab(state.activeTab);
  }
}

function renderRunActivity() {
  const run = state.run;
  const terminal = !["PENDING", "RUNNING"].includes(run.status);
  const completed = (run.steps || []).map(renderActivity).join("");
  const live = terminal ? "" : runningActivity(run.active_stage ? `${stageLabel(run.active_stage)} 已写入检查点，正在继续` : "后台任务已启动");
  elements.activityFeed.innerHTML = completed + live;
  const failedSteps = (run.steps || []).filter((step) => step.status === "FAILED").length;
  elements.activitySummary.textContent = terminal
    ? (failedSteps ? `${failedSteps} 个阶段需要处理` : "全部阶段已完成")
    : `已完成 ${(run.steps || []).length} 个阶段`;
  setRunState(run.status.toLowerCase(), statusLabel(run.status));
}

function finishRun() {
  stopElapsedTimer();
  elements.startButton.disabled = false;
  loadRecentRuns();
}

function startElapsedTimer() {
  stopElapsedTimer();
  state.runStartedAt = Date.now();
  state.elapsedTimer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - state.runStartedAt) / 1000);
    const target = document.querySelector("#run-elapsed");
    if (target) target.textContent = `${elapsed} 秒`;
  }, 1000);
}

function stopElapsedTimer() {
  if (state.elapsedTimer) clearInterval(state.elapsedTimer);
  state.elapsedTimer = null;
}

function renderActivity(step) {
  const failed = step.status === "FAILED";
  return `
    <article class="activity-item ${failed ? "failed" : ""}">
      <span class="activity-marker" aria-hidden="true"></span>
      <div class="activity-meta">
        <strong>${escapeHtml(stageLabel(step.stage))}</strong>
        <span>${formatDuration(step.duration_ms)}</span>
      </div>
      <p>${escapeHtml(step.summary)}</p>
      ${step.error ? `<p class="activity-error">${escapeHtml(step.error)}</p>` : ""}
    </article>`;
}

function runningActivity(message) {
  const provider = elements.provider.options[elements.provider.selectedIndex]?.text || elements.provider.value;
  const model = elements.model.value.trim() || "服务端默认模型";
  return `
    <article class="activity-item running">
      <span class="activity-marker" aria-hidden="true"></span>
      <div class="activity-meta"><strong>VibeProof</strong><span id="run-elapsed">0 秒</span></div>
      <p>${escapeHtml(message)}。服务端正在使用 ${escapeHtml(provider)} / ${escapeHtml(model)} 执行接管。</p>
    </article>`;
}

function selectTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
  if (!state.report) return;
  const renderers = {
    overview: renderOverview,
    evidence: renderEvidence,
    learning: renderLearning,
    runtime: renderRuntime,
  };
  elements.resultContent.innerHTML = renderers[tab]();
  bindEvidenceButtons();
}

function renderOverview() {
  const report = state.report;
  const repository = report.repository || {};
  const architecture = report.architecture || {};
  const learning = report.learning_plan || {};
  const runtime = report.runtime || {};
  const language = Object.entries(repository.languages || {}).sort((a, b) => b[1] - a[1])[0]?.[0] || "—";
  const warnings = report.warnings || [];
  return `
    <div class="result-actions">
      <a class="secondary-button" href="/api/v1/runs/${encodeURIComponent(state.run.run_id)}/export?format=json">导出 JSON</a>
      <a class="secondary-button" href="/api/v1/runs/${encodeURIComponent(state.run.run_id)}/export?format=markdown">导出 Markdown</a>
      <button class="secondary-button" type="button" data-action="retry-learning">重跑 Tutor</button>
      <button class="secondary-button" type="button" data-action="retry-runtime">重跑 Runtime</button>
      <button class="danger-button" type="button" data-action="delete-run">删除记录</button>
    </div>
    <div class="summary-block">
      <h2>${escapeHtml(report.repository_name)}</h2>
      <p>${escapeHtml(report.summary)}</p>
    </div>
    <div class="metric-grid">
      ${metric(repository.scanned_files ?? 0, "扫描文件")}
      ${metric(language, "主要语言")}
      ${metric((architecture.claims || []).length, "已验证结论")}
      ${metric((learning.units || []).length, "学习单元")}
    </div>
    ${chipSection("入口文件", repository.entrypoints)}
    ${chipSection("测试文件", repository.test_files)}
    ${chipSection("框架", repository.frameworks)}
    <h3 class="subsection-title">运行验证</h3>
    <div class="runtime-card">
      <div class="runtime-topline">
        <span class="runtime-status ${(runtime.status || "unknown").toLowerCase()}">${escapeHtml(runtime.status || "NOT AVAILABLE")}</span>
        <span class="claim-confidence">${runtime.executed ? "已执行" : "仅生成计划"}</span>
      </div>
      <p class="claim-source">${escapeHtml((runtime.plan?.command || []).join(" ") || "没有运行计划")}</p>
    </div>
    ${warnings.length ? `<h3 class="subsection-title">警告</h3><div class="warning-list">${warnings.map((item) => `<div class="warning-card"><p>${escapeHtml(item)}</p></div>`).join("")}</div>` : ""}`;
}

function renderEvidence() {
  const architecture = state.report.architecture;
  if (!architecture) return emptyResult("架构分析没有生成报告。");
  const accepted = architecture.claims || [];
  const rejected = architecture.rejected_claims || [];
  const trace = architecture.trace || [];
  return `
    <div class="summary-block">
      <h2>架构证据</h2>
      <p>${escapeHtml(architecture.summary)}</p>
    </div>
    <h3 class="subsection-title">已验证结论 · ${accepted.length}</h3>
    <div class="claim-list">${accepted.length ? accepted.map((claim) => claimCard(claim, false)).join("") : emptyResult("暂无已验证结论。")}</div>
    <h3 class="subsection-title">已拒绝结论 · ${rejected.length}</h3>
    <div class="claim-list">${rejected.length ? rejected.map((claim) => claimCard(claim, true)).join("") : emptyResult("没有被拒绝的结论。")}</div>
    <h3 class="subsection-title">Analyst 检索轨迹 · ${trace.length}</h3>
    <div class="trace-list">${trace.length ? trace.map(renderTraceStep).join("") : emptyResult("没有记录检索轨迹。")}</div>
    ${(architecture.unresolved_questions || []).length ? `<h3 class="subsection-title">待解决问题</h3><div class="warning-list">${architecture.unresolved_questions.map((item) => `<div class="warning-card"><p>${escapeHtml(item)}</p></div>`).join("")}</div>` : ""}`;
}

function renderTraceStep(step) {
  const returned = step.returned_evidence_ids?.length || 0;
  return `<article class="trace-card ${step.error ? "failed" : ""}">
    <div class="trace-topline"><strong>步骤 ${step.step} · ${escapeHtml(step.action)}</strong><span>${returned} 条证据</span></div>
    <code>${escapeHtml(step.query || step.message || "完成架构结论")}</code>
    ${step.error ? `<p>${escapeHtml(step.error)}</p>` : ""}
  </article>`;
}

function claimCard(claim, rejected) {
  const evidenceId = claim.evidence_ids?.[0] || "";
  const reference = findEvidence(evidenceId);
  const location = reference ? `${reference.path}:${reference.start_line}-${reference.end_line}` : evidenceId || "没有源码引用";
  return `
    <button class="claim-card ${rejected ? "rejected" : ""}" type="button" data-evidence-id="${escapeAttribute(evidenceId)}" data-claim="${escapeAttribute(claim.claim)}">
      <div class="claim-topline">
        <span class="claim-status ${rejected ? "rejected" : "verified"}">${rejected ? "已拒绝" : "已验证"}</span>
        <span class="claim-confidence">置信度 ${Math.round((claim.confidence || 0) * 100)}%</span>
      </div>
      <p>${escapeHtml(claim.claim)}</p>
      <span class="claim-source">${escapeHtml(location)}</span>
    </button>`;
}

function renderLearning() {
  const plan = state.report.learning_plan;
  if (!plan) return emptyResult("完成架构分析后才能生成学习计划。");
  const attempts = state.run?.attempts || [];
  const latest = attempts.at(-1)?.review;
  const assessments = new Map((latest?.assessments || []).map((item) => [item.question_id, item]));
  const questionsByUnit = new Map();
  (plan.questions || []).forEach((question) => {
    const items = questionsByUnit.get(question.unit_sequence) || [];
    items.push(question);
    questionsByUnit.set(question.unit_sequence, items);
  });
  return `
    <div class="summary-block"><h2>学习路径</h2><p>${escapeHtml(plan.summary)}</p></div>
    ${latest ? `<div class="progress-card">
      <strong>第 ${attempts.length} 次学习记录</strong>
      <span>完成度 ${latest.progress.completion_percent.toFixed(1)}% · 掌握度 ${latest.progress.mastery_percent.toFixed(1)}%</span>
      <small>${escapeHtml(latest.mode === "MODEL_ASSESSED" ? "模型已按源码证据评审" : "Mock 仅检查提交结构")}</small>
    </div>` : ""}
    <div class="learning-list">
      ${(plan.units || []).map((unit) => {
        const questions = questionsByUnit.get(unit.sequence) || [];
        return `<article class="learning-card">
          <div class="learning-topline"><h3>${escapeHtml(unit.title)}</h3><span class="learning-sequence">单元 ${unit.sequence}</span></div>
          <p><span class="learning-label">学习目标 · </span>${escapeHtml(unit.objective)}</p>
          <p><span class="learning-label">练习 · </span>${escapeHtml(unit.exercise)}</p>
          ${questions.map((question) => {
            const assessment = assessments.get(question.question_id);
            return `<div class="quiz-question">
              <label for="answer-${escapeAttribute(question.question_id)}"><span class="learning-label">验收问题 · </span>${escapeHtml(question.prompt)}</label>
              <textarea id="answer-${escapeAttribute(question.question_id)}" data-question-id="${escapeAttribute(question.question_id)}" rows="4" placeholder="用你自己的话解释，并尽量引用具体调用链。"></textarea>
              ${assessment ? `<div class="assessment ${assessment.status.toLowerCase()}">
                <strong>${escapeHtml(statusLabel(assessment.status))}${assessment.score === null ? "" : ` · ${assessment.score} 分`}</strong>
                <p>${escapeHtml(assessment.feedback)}</p>
              </div>` : ""}
            </div>`;
          }).join("")}
          <span class="learning-evidence">${escapeHtml((unit.evidence_ids || []).join(", "))}</span>
        </article>`;
      }).join("") || emptyResult("没有生成基于源码证据的学习单元。")}
    </div>
    <div class="review-actions">
      <span>提交后会保留本次记录；再次作答不会覆盖历史。</span>
      <button class="primary-button" type="button" data-action="submit-review">提交答案并评审</button>
    </div>`;
}

function renderRuntime() {
  const runtime = state.report.runtime;
  if (!runtime) return emptyResult("运行验证没有生成报告。");
  const command = (runtime.plan?.command || []).join(" ");
  const evidence = runtime.evidence;
  const output = evidence ? [evidence.stdout_excerpt, evidence.stderr_excerpt].filter(Boolean).join("\n") : "未请求执行命令。";
  return `
    <div class="summary-block"><h2>运行验证</h2><p>固定命令目录让运行证据保持可复现、可审查。</p></div>
    <div class="runtime-card">
      <div class="runtime-topline">
        <span class="runtime-status ${(runtime.status || "").toLowerCase()}">${escapeHtml(runtime.status)}</span>
        <span class="claim-confidence">${evidence ? formatDuration(evidence.duration_ms) : "未执行"}</span>
      </div>
      <pre class="terminal">$ ${escapeHtml(command)}\n\n${escapeHtml(output || "No output captured.")}</pre>
    </div>
    <div class="metric-grid">
      ${metric(evidence?.exit_code ?? "—", "退出码")}
      ${metric(runtime.repository_changed ? "是" : "否", "仓库发生变化")}
      ${metric(evidence?.scrubbed_environment_variables ?? "—", "已清理敏感变量")}
      ${metric(runtime.plan?.check || "—", "检查类型")}
    </div>`;
}

function bindEvidenceButtons() {
  document.querySelectorAll("[data-evidence-id]").forEach((button) => {
    button.addEventListener("click", () => openEvidence(button.dataset.evidenceId, button.dataset.claim));
  });
}

async function openEvidence(evidenceId, claim) {
  const reference = findEvidence(evidenceId);
  elements.inspector.classList.remove("closed");
  if (!reference) {
    elements.inspectorTitle.textContent = "引用不可用";
    elements.inspectorBody.innerHTML = `<div class="inspector-empty"><p>这条结论没有引用当前报告中的源码证据。</p></div>`;
    return;
  }

  elements.inspectorTitle.textContent = reference.symbol || reference.path;
  elements.inspectorBody.innerHTML = `
    <div class="evidence-meta"><span class="eyebrow">正在加载源码</span><p>${escapeHtml(claim)}</p><span class="evidence-path">${escapeHtml(reference.path)}:${reference.start_line}-${reference.end_line}</span></div>
    <div class="inspector-empty"><p>正在读取已验证的源码范围…</p></div>`;
  try {
    const response = await fetch("/api/v1/repositories/source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        relativePath: state.relativePath,
        sourcePath: reference.path,
        startLine: reference.start_line,
        endLine: reference.end_line,
      }),
    });
    const body = await parseResponse(response);
    if (!response.ok) throw new Error(body.detail || "无法读取源码证据");
    elements.inspectorBody.innerHTML = `
      <div class="evidence-meta">
        <span class="claim-status verified">已验证源码</span>
        <p>${escapeHtml(claim)}</p>
        <span class="evidence-path">${escapeHtml(body.sourcePath)}:${body.startLine}-${body.endLine}</span>
      </div>
      <div class="code-view">${renderCode(body.content, body.startLine)}</div>`;
  } catch (error) {
    elements.inspectorBody.innerHTML = `<div class="inspector-empty"><p>${escapeHtml(error.message)}</p></div>`;
  }
}

function findEvidence(evidenceId) {
  if (!evidenceId || !state.report?.architecture) return null;
  return (state.report.architecture.evidence || []).find((item) => item.chunk_id === evidenceId) || null;
}

function renderCode(content, startLine) {
  return content.split("\n").map((line, index) => `
    <div class="code-line"><span class="code-number">${startLine + index}</span><span class="code-content">${escapeHtml(line) || " "}</span></div>`).join("");
}

function renderRequestFailure(error) {
  elements.activityFeed.innerHTML = `
    <article class="activity-item failed">
      <span class="activity-marker" aria-hidden="true"></span>
      <div class="activity-meta"><strong>请求失败</strong><span>已停止</span></div>
      <p class="activity-error">${escapeHtml(error.message)}</p>
    </article>`;
  elements.activitySummary.textContent = "需要处理";
  setRunState("failed", "失败");
  showToast(error.message);
}

function resetWorkspace() {
  clearTimeout(state.pollTimer);
  stopElapsedTimer();
  state.run = null;
  state.report = null;
  state.relativePath = "";
  elements.welcome.classList.remove("hidden");
  elements.runView.classList.add("hidden");
  elements.resultSection.classList.add("hidden");
  elements.repositoryTitle.textContent = "新任务";
  elements.inspector.classList.remove("closed");
  elements.inspectorTitle.textContent = "证据检查器";
  elements.inspectorBody.innerHTML = `<div class="inspector-empty"><div class="file-glyph" aria-hidden="true">{ }</div><p>选择一条已验证结论，查看对应的源码位置。</p></div>`;
  setRunState("idle", "空闲");
}

async function loadRecentRuns() {
  try {
    const response = await fetch("/api/v1/runs?limit=12");
    const body = await parseResponse(response);
    if (!response.ok) throw new Error(body.detail || "无法读取历史任务");
    state.recentRuns = body;
    renderRecentRuns();
  } catch (error) {
    elements.recentRuns.innerHTML = `<p class="sidebar-empty">${escapeHtml(error.message)}</p>`;
  }
}

async function openRecentRun(event) {
  const button = event.target.closest("[data-run-id]");
  if (!button) return;
  try {
    const response = await fetch(`/api/v1/runs/${encodeURIComponent(button.dataset.runId)}`);
    const body = await parseResponse(response);
    if (!response.ok) throw new Error(body.detail || "无法打开历史任务");
    clearTimeout(state.pollTimer);
    applyRun(body);
    if (["PENDING", "RUNNING"].includes(body.status)) {
      startElapsedTimer();
      pollRun(body.run_id);
    }
  } catch (error) {
    showToast(error.message);
  }
}

function renderRecentRuns() {
  if (!state.recentRuns.length) {
    elements.recentRuns.innerHTML = `<p class="sidebar-empty">完成接管后会显示在这里。</p>`;
    return;
  }
  elements.recentRuns.innerHTML = state.recentRuns.map((run) => `
    <button class="recent-run ${run.run_id === state.run?.run_id ? "active" : ""}" type="button" data-run-id="${escapeAttribute(run.run_id)}">
      <strong>${escapeHtml(run.repository_name)}</strong>
      <span>${escapeHtml(statusLabel(run.status))} · ${formatDate(run.updated_at)}</span>
    </button>`).join("");
}

async function handleResultAction(event) {
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (!action || !state.run) return;
  if (action === "submit-review") await submitReview();
  if (action === "retry-learning") await retryStage("learning");
  if (action === "retry-runtime") await retryStage("runtime");
  if (action === "delete-run") await deleteCurrentRun();
}

async function submitReview() {
  const button = elements.resultContent.querySelector('[data-action="submit-review"]');
  const answers = [...elements.resultContent.querySelectorAll("[data-question-id]")].map((field) => ({
    question_id: field.dataset.questionId,
    answer: field.value.trim(),
  }));
  button.disabled = true;
  button.textContent = "评审中…";
  try {
    const payload = {
      answers,
      provider: state.run.configuration.provider,
      model: state.run.configuration.model,
    };
    if (!payload.model) delete payload.model;
    const response = await fetch(`/api/v1/runs/${encodeURIComponent(state.run.run_id)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await parseResponse(response);
    if (!response.ok) throw new Error(body.detail || "答案评审失败");
    const refreshed = await fetch(`/api/v1/runs/${encodeURIComponent(state.run.run_id)}`);
    applyRun(await parseResponse(refreshed));
    showToast("本轮答案和证据化评审已保存");
  } catch (error) {
    showToast(error.message);
    button.disabled = false;
    button.textContent = "提交答案并评审";
  }
}

async function retryStage(stage) {
  try {
    const response = await fetch(`/api/v1/runs/${encodeURIComponent(state.run.run_id)}/retry`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stage }),
    });
    const body = await parseResponse(response);
    if (!response.ok) throw new Error(body.detail || "阶段重试失败");
    startElapsedTimer();
    applyRun(body);
    await pollRun(body.run_id);
  } catch (error) {
    showToast(error.message);
  }
}

async function deleteCurrentRun() {
  if (!window.confirm("删除这条本地接管记录？源码仓库不会被修改。")) return;
  try {
    const response = await fetch(`/api/v1/runs/${encodeURIComponent(state.run.run_id)}`, { method: "DELETE" });
    if (!response.ok) {
      const body = await parseResponse(response);
      throw new Error(body.detail || "删除失败");
    }
    resetWorkspace();
    await loadRecentRuns();
    showToast("历史记录已删除");
  } catch (error) {
    showToast(error.message);
  }
}

function setRunState(kind, label) {
  elements.runState.className = `run-state ${kind}`;
  elements.runStateLabel.textContent = label;
}

function updateProviderLabel() {
  const label = elements.provider.options[elements.provider.selectedIndex]?.text || elements.provider.value;
  elements.sidebarProvider.textContent = label;
}

function metric(value, label) {
  return `<div class="metric"><strong title="${escapeAttribute(String(value))}">${escapeHtml(String(value))}</strong><span>${escapeHtml(label)}</span></div>`;
}

function chipSection(title, items) {
  if (!items?.length) return "";
  return `<h3 class="subsection-title">${escapeHtml(title)}</h3><div class="chip-list">${items.map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}</div>`;
}

function emptyResult(message) {
  return `<div class="empty-result">${escapeHtml(message)}</div>`;
}

async function parseResponse(response) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch (_) {
    return { detail: text || response.statusText };
  }
}

function stageLabel(stage) {
  const labels = {
    SCAN: "仓库扫描 · Scanner",
    INDEX: "源码索引 · Indexer",
    ANALYZE: "架构分析 · Analyst",
    LEARNING_PLAN: "学习规划 · Tutor",
    RUNTIME_PLAN: "运行计划 · Runtime",
    RUNTIME_EXECUTION: "运行验证 · Runtime",
    REPORT: "接管报告 · Coordinator",
  };
  return labels[stage] || titleCase(stage);
}

function statusLabel(status) {
  const labels = {
    PENDING: "等待中",
    RUNNING: "运行中",
    COMPLETED: "已完成",
    PARTIAL: "部分完成",
    FAILED: "失败",
    SNAPSHOT_CHANGED: "源码快照已变化",
    PLANNED: "已规划",
    PASSED: "已通过",
    ANSWERED: "已掌握",
    NEEDS_IMPROVEMENT: "需要改进",
    NOT_ASSESSED: "未评分",
    REJECTED: "评审被拒绝",
  };
  return labels[status] || titleCase(status);
}

function titleCase(value) {
  return String(value || "").toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function leafName(path) {
  return path.replaceAll("\\", "/").split("/").filter(Boolean).pop() || path;
}

function formatDuration(milliseconds) {
  if (!milliseconds) return "< 1 ms";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  return `${(milliseconds / 1000).toFixed(1)} s`;
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "最近" : date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

let toastTimer;
function showToast(message) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  toastTimer = setTimeout(() => elements.toast.classList.add("hidden"), 5000);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}
