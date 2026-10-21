/* Talent Compass 匹配工作台 — 前端交互（无构建依赖，vanilla JS） */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

const STATE = {
  decisionLabels: {},
  sourceLabels: {},
  employees: [],
  jobs: [],
  lastResults: null,
};

/* ── 工具 ── */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

function countUp(el, target, decimals = 1, ms = 900) {
  const t0 = performance.now();
  const tick = (t) => {
    const p = Math.min(1, (t - t0) / ms);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = (target * eased).toFixed(decimals);
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/* 进场动画 */
const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }
}, { threshold: 0.08 });

/* ── 初始化 ── */
async function init() {
  try {
    const [stateRes, empRes, jobRes] = await Promise.all([
      fetch("/api/state"), fetch("/api/employees"), fetch("/api/jobs"),
    ]);
    const state = await stateRes.json();
    const empData = await empRes.json();
    const jobData = await jobRes.json();
    STATE.decisionLabels = state.decision_labels;
    STATE.sourceLabels = state.source_labels;
    STATE.employees = empData.employees;
    STATE.jobs = jobData.jobs;

    $("#navMeta").textContent = `${state.n_employees} 人 · ${state.parse_mode.split("（")[0]}`;
    $("#footModels").textContent =
      `${state.embedding_model} + ${state.reranker_model} · 阈值 ${state.thresholds.reject}/${state.thresholds.review}`;
    renderGoldChips();
    renderEmpGrid();
    $$(".reveal").forEach((el) => io.observe(el));
  } catch (err) {
    console.error("init failed", err);
    $("#navMeta").textContent = "后端连接失败";
  }
}

/* ── 示例岗位 ── */
function renderGoldChips() {
  const box = $("#goldChips");
  box.innerHTML = STATE.jobs.map((j, i) =>
    `<button type="button" class="chip" data-idx="${i}">${esc(j.title)}</button>`
  ).join("");
  $$(".chip", box).forEach((chip) => {
    chip.addEventListener("click", () => {
      const j = STATE.jobs[+chip.dataset.idx];
      $("#jobTitle").value = j.title;
      $("#jobResp").value = (j.responsibilities || []).join("\n");
      $("#jobReq").value = (j.requirements || []).join("\n");
    });
  });
}

/* ── 匹配 ── */
$("#matchForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const payload = {
    title: $("#jobTitle").value.trim(),
    responsibilities: $("#jobResp").value.split("\n").map((s) => s.trim()).filter(Boolean),
    requirements: $("#jobReq").value.split("\n").map((s) => s.trim()).filter(Boolean),
    top_k: +$("#topK").value,
  };
  if (!payload.responsibilities.length && !payload.requirements.length) {
    alert("请填写工作职责或任职要求（也可点选示例岗位）");
    return;
  }
  setLoading(true, "构建岗位画像 · 全员向量检索 · cross-encoder 校准…");
  try {
    const t0 = performance.now();
    const res = await fetch("/api/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    // 最少转场 600ms，避免闪屏
    const remain = Math.max(0, 600 - (performance.now() - t0));
    setTimeout(() => { renderResults(data); setLoading(false); }, remain);
  } catch (err) {
    setLoading(false);
    alert("匹配失败：" + err.message);
  }
});

function setLoading(on, text) {
  $("#matchBtn").disabled = on;
  $("#matchEmpty").classList.toggle("hidden", on);
  $("#matchResults").classList.toggle("hidden", on);
  $("#matchLoading").classList.toggle("hidden", !on);
  if (text) $("#loadingText").textContent = text;
}

function renderResults(data) {
  STATE.lastResults = data;
  $("#matchEmpty").classList.add("hidden");
  $("#matchResults").classList.remove("hidden");
  $("#resultJobTitle").textContent = data.job.title;
  const s = data.summary, dc = s.decision_counts;
  $("#resultStats").innerHTML = `
    <span class="stat-pill">候选 <b>${s.n_candidates}</b> 人</span>
    <span class="stat-pill">自动推荐 <b>${dc.recommend}</b></span>
    <span class="stat-pill">待审 <b>${dc.review}</b></span>
    <span class="stat-pill">备选池 <b>${dc.backup_pool}</b></span>
    <span class="stat-pill">未通过 <b>${dc.rejected}</b></span>
    <span class="stat-pill">耗时 <b>${s.duration_ms}</b>ms</span>`;

  const strip = $("#parsedStrip");
  const hard = data.job.hard_requirements || {};
  const hardBits = [
    hard.education_min ? `学历≥${hard.education_min}` : null,
    hard.years_min ? `年限≥${hard.years_min}年` : null,
    ...(hard.certificates || []),
  ].filter(Boolean);
  strip.innerHTML = `
    <div class="p-label">引擎解析的岗位画像（${esc(data.job.parse_source)}）</div>
    <div class="parsed-tags">
      ${hardBits.map((h) => `<span class="ptag hard">闸门 · ${esc(h)}</span>`).join("")}
      ${(data.job.skill_requirements || []).slice(0, 12).map((r) =>
        `<span class="ptag">${esc(r.name)}</span>`).join("")}
    </div>`;

  const list = $("#cardList");
  list.innerHTML = "";
  data.candidates.forEach((c, i) => list.appendChild(renderCard(c, i)));
  $$(".reveal", $("#matchResults")).forEach((el) => io.observe(el));
  $$(".cand", list).forEach((el) => {
    el.style.animationDelay = `${Math.min(i0(el), 8) * 70}ms`;
  });
}

function i0(el) { return +el.dataset.rank - 1 || 0; }

function renderCard(c, idx) {
  const el = document.createElement("article");
  el.className = `cand bezel rank-${idx + 1}`;
  el.dataset.rank = idx + 1;
  const s = c.scores;
  const gates = (c.gate && !c.gate.passed)
    ? `<span class="badge rejected" title="${esc((c.gate.fail_reasons || []).join("；"))}">闸门拦截</span>` : "";
  el.innerHTML = `
    <div class="cand-inner">
      <div class="cand-top">
        <div class="rank">${idx + 1}</div>
        <div class="cand-id">
          <div class="cand-name-row">
            <span class="cand-name">${esc(c.name || c.emp_id)}</span>
            <span class="cand-meta">${esc(c.emp_id)}</span>
            <span class="badge ${c.decision}">${esc(STATE.decisionLabels[c.decision] || c.decision)}</span>
            ${gates}
            ${c.ce_calibrated ? '<span class="badge clickable" style="color:var(--accent-2);border:1px solid rgba(95,212,196,.3);background:rgba(95,212,196,.06)" title="Top-10 候选经 bge-reranker 交叉校准">CE 校准</span>' : ""}
          </div>
          <div class="emp-sub" style="margin-top:.35rem" data-emp="${esc(c.emp_id)}"></div>
        </div>
        <div class="score-box top-score" title="公式原始分 ${s.total}（金标锚定映射后的展示分）">
          <div class="score-num" data-target="${c.display_score ?? s.total}">0</div>
          <div class="score-sub">综合匹配 / 100</div>
        </div>
      </div>
      <div class="cand-body">
        <div class="score-box" style="padding:.9rem .6rem">
          ${barRow("t0", "T0 直接技能", s.t0, 50)}
          ${barRow("t1", "T1 语义匹配", s.t1, 30)}
          ${barRow("t2", "T2 行为能力", s.t2, 10)}
          ${barRow("t3", "T3 发展潜力", s.t3, 10)}
        </div>
        <div>
          <div class="reason">${renderReason(c.reason)}</div>
          ${renderEvidence(c)}
        </div>
      </div>
    </div>`;
  // 拉员工摘要行
  const emp = STATE.employees.find((e) => e.employee_id === c.emp_id);
  if (emp) {
    $(".emp-sub", el).textContent =
      `${emp.position || "—"} · ${emp.level || "—"} · ${emp.job_sequence || "—"} · ${emp.years ?? "—"} 年 · 360 均分 ${emp.s360_avg ?? "—"}`;
  }
  // 动画挂载后触发
  requestAnimationFrame(() => {
    const num = $(".score-num", el);
    countUp(num, parseFloat(num.dataset.target), 1);  // 动画终点 = data-target（展示分），勿用原始分覆盖
    $$(".bar-fill", el).forEach((b) => { b.style.width = b.dataset.w + "%"; });
  });
  // 证据折叠 + 溯源
  const tog = $(".evi-toggle", el);
  tog.addEventListener("click", () => {
    tog.classList.toggle("open");
    $(".evi-list", el).classList.toggle("open");
  });
  $$(".trace-btn", el).forEach((btn) => {
    btn.addEventListener("click", () => openTrace(c, +btn.dataset.evi));
  });
  return el;
}

function barRow(cls, label, val01, full) {
  const pts = (val01 * full).toFixed(1);
  const pct = Math.min(100, val01 * 100).toFixed(1);
  return `<div class="bar-row ${"b-" + cls}">
    <span class="bar-label">${label}</span>
    <div class="bar-track"><div class="bar-fill" data-w="${pct}"></div></div>
    <span class="bar-val">${pts}/${full}</span>
  </div>`;
}

function renderReason(reason) {
  // 「字面命中技能证据 N 项（如「X」）；语义最相关证据：anchor…（sim 0.xx）；T1语义 …」
  return esc(reason).replace(/（如「([^」]+)」）/g, "（如「<b>$1</b>」）");
}

function renderEvidence(c) {
  const evs = c.evidence || [];
  if (!evs.length) return "";
  return `<div class="evi-wrap">
    <button type="button" class="evi-toggle"><span class="arr">▶</span> 证据链 · ${evs.length} 条（点开逐条溯源）</button>
    <div class="evi-list">
      ${evs.map((e, i) => `
        <div class="evi-item">
          <div class="evi-src">${esc(STATE.sourceLabels[e.source] || e.source)}</div>
          <div class="evi-text">
            <span class="q">命中要求：<b>${esc(e.query)}</b></span>
            ${esc(e.text.length > 160 ? e.text.slice(0, 160) + "…" : e.text)}
          </div>
          <div><div class="evi-sim">sim ${e.sim.toFixed(2)}</div>
            <button type="button" class="trace-btn" data-emp="${esc(c.emp_id)}" data-evi="${i}">溯源 ↗</button>
          </div>
        </div>`).join("")}
    </div>
  </div>`;
}

/* ── 溯源弹层：证据原文 + 员工完整原始记录 ── */
async function openTrace(cand, eviIdx) {
  const evi = (cand.evidence || [])[eviIdx];
  if (!evi) return;
  $("#traceTitle").textContent = `证据溯源 · ${cand.name || cand.emp_id}`;
  $("#traceBody").innerHTML = `<div class="trace-q">匹配要求：<b>${esc(evi.query)}</b>　·　相似度 ${evi.sim.toFixed(3)}（bge 语义空间）</div>
    <div class="trace-block"><span class="trace-src">${esc(STATE.sourceLabels[evi.source] || evi.source)}</span>
      <div class="trace-anchor">锚点「${esc(evi.anchor)}…」</div>
      <div class="trace-text">${esc(evi.text)}</div>
      <div class="trace-full"><span class="fl">LOADING ORIGINAL…</span></div>
    </div>`;
  $("#traceModal").classList.remove("hidden");
  // 拉原始记录全文（截断的证据 → 完整原文）
  try {
    const res = await fetch(`/api/employees/${encodeURIComponent(cand.emp_id)}`);
    const emp = await res.json();
    const full = fullTextFor(emp, evi);
    $(".trace-full", $("#traceBody")).innerHTML =
      `<span class="fl">原始记录 · ${esc(STATE.sourceLabels[evi.source] || evi.source)}（完整）</span>${full}
       <button class="trace-link" id="openProfile">打开 ${esc(emp.summary.name || cand.emp_id)} 完整档案 →</button>`;
    $("#openProfile").addEventListener("click", () => {
      closeTrace();
      openDrawer(cand.emp_id);
    });
  } catch { $(".trace-full", $("#traceBody")).innerHTML = ""; }
}

function fullTextFor(emp, evi) {
  const escFull = (items, fmt) => items.length
    ? items.map(fmt).join("") : "<span style='color:var(--ink-faint)'>（无记录）</span>";
  switch (evi.source) {
    case "projects":
      return escFull(emp.projects || [], (p) =>
        `<div style="margin-bottom:.5rem"><b>${esc(p.project_name)}</b> · ${esc(p.role || "")}${(p.tools || []).length ? " · 工具 " + esc(p.tools.join("/")) : ""}<br>${esc(p.description || "")}</div>`);
    case "performance":
      return escFull(emp.performance || [], (p) =>
        `<div style="margin-bottom:.4rem"><b>${esc(p.year)}年 ${esc(p.grade)}</b>　${esc(p.comment || "")}</div>`);
    case "training":
      return escFull(emp.training || [], (t) =>
        `<div style="margin-bottom:.4rem"><b>${esc(t.course_name)}</b>　${esc(t.status || "")}${t.score ? " · " + t.score + " 分" : ""}</div>`);
    case "position": {
      const st = emp.structured || {};
      return `岗位 <b>${esc(st.current_position || "—")}</b> · 序列 ${esc(st.job_sequence || "—")} · 专业 ${esc(st.major || "—")} · 证书 <b>${esc(st.certificates || "无")}</b>`;
    }
    case "summary_performance":
      return esc(emp.text_summaries?.performance_summary || "（无）");
    case "summary_project":
      return esc(emp.text_summaries?.project_summary || "（无）");
    case "summary_evaluation":
      return escFull(
        (emp.text_summaries?.evaluation_summary || "").split("；").filter(Boolean),
        (s) => `<div>· ${esc(s)}</div>`);
    default:
      return esc(evi.text);
  }
}

function closeTrace() { $("#traceModal").classList.add("hidden"); }
$("#traceClose").addEventListener("click", closeTrace);
$("#traceModal").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeTrace(); });

/* ── 员工库 ── */
function renderEmpGrid(filter = "") {
  const grid = $("#empGrid");
  const q = filter.trim().toLowerCase();
  const list = STATE.employees.filter((e) =>
    !q || [e.name, e.position, e.job_sequence, e.employee_id]
      .some((v) => String(v || "").toLowerCase().includes(q)));
  grid.innerHTML = "";
  list.forEach((e, i) => {
    const el = document.createElement("article");
    el.className = "emp-card bezel";
    el.style.animationDelay = `${Math.min(i, 12) * 45}ms`;
    const trend = (e.performance_trend || []).map((g) =>
      `<span class="trend-dot g${{ A: 4, B: 3, C: 2, D: 1 }[g] || 0}" title="${esc(g)}">${esc(g)}</span>`).join("");
    el.innerHTML = `<div class="cand-inner">
      <div class="emp-name">${esc(e.name || e.employee_id)}</div>
      <div class="emp-sub">${esc(e.position || "—")} · ${esc(e.level || "—")}</div>
      <div class="emp-trend">${trend || "<span style='color:var(--ink-faint);font-size:.7rem'>无绩效记录</span>"}</div>
      <div class="emp-foot"><span>${esc(e.job_sequence || "—")}</span><span>${e.years ?? "—"} 年 · 证据 ${e.n_evidence}</span></div>
    </div>`;
    el.addEventListener("click", () => openDrawer(e.employee_id));
    grid.appendChild(el);
  });
  if (!list.length) grid.innerHTML = "<p style='color:var(--ink-faint)'>无匹配员工</p>";
}
$("#empSearch").addEventListener("input", (e) => renderEmpGrid(e.target.value));

/* ── 员工档案抽屉 ── */
async function openDrawer(empId) {
  const res = await fetch(`/api/employees/${encodeURIComponent(empId)}`);
  const emp = await res.json();
  const s = emp.summary, st = emp.structured || {};
  $("#drawerTitle").innerHTML = `
    <span class="eyebrow">EMPLOYEE PROFILE</span>
    <h3 style="font-size:1.3rem;margin-top:.5rem">${esc(s.name || empId)}
      <span style="font-size:.78rem;color:var(--ink-faint);font-family:var(--mono)">${esc(empId)}</span></h3>`;
  const trend = (s.performance_trend || []).map((g) =>
    `<span class="trend-dot g${{ A: 4, B: 3, C: 2, D: 1 }[g] || 0}">${esc(g)}</span>`).join(" → ");
  const s360 = emp.scores_360 || {};
  const s360max = Math.max(1, ...Object.values(s360).map((v) => +v || 0), 5);
  $("#drawerBody").innerHTML = `
    <div class="sec"><div class="sec-title">基本信息</div>
      <div class="kv-grid">
        ${kv("岗位", st.current_position)}${kv("职级", st.current_level)}
        ${kv("序列", st.job_sequence)}${kv("学历", st.education)}
        ${kv("专业", st.major)}${kv("司龄", st.years_of_service != null ? st.years_of_service + " 年" : "—")}
        ${kv("证书", st.certificates)}${kv("政治面貌", st.political_status)}
      </div>
    </div>
    <div class="sec"><div class="sec-title">绩效轨迹</div>
      <div style="display:flex;align-items:center;gap:.5rem">${trend || "（无记录）"}</div>
    </div>
    <div class="sec"><div class="sec-title">360 评价（五维）</div>
      ${Object.entries(s360).map(([k, v]) => `
        <div class="s360-row"><span style="font-size:.76rem;color:var(--ink-dim)">${esc(k)}</span>
          <div class="bar-track"><div class="bar-fill b-t1" data-w="${(v / s360max * 100).toFixed(1)}" style="background:linear-gradient(90deg,#5fd4c4,#6fd6ef)"></div></div>
          <span class="bar-val">${(+v).toFixed(1)}</span></div>`).join("") || "（无）"}
    </div>
    <div class="sec"><div class="sec-title">项目经历</div>
      <div class="item-list">${(emp.projects || []).map((p) =>
        `<div class="item-card"><b>${esc(p.project_name)}</b> · ${esc(p.role || "")}${(p.tools || []).length ? "<br>工具：" + esc(p.tools.join(" / ")) : ""}<br>${esc(p.description || "")}</div>`).join("") || "（无）"}</div>
    </div>
    <div class="sec"><div class="sec-title">培训记录</div>
      <div class="item-list">${(emp.training || []).map((t) =>
        `<div class="item-card"><b>${esc(t.course_name)}</b>　${esc(t.status || "")}${t.score ? " · " + t.score + " 分" : ""}</div>`).join("") || "（无）"}</div>
    </div>
    <div class="sec"><div class="sec-title">证据切片（向量索引素材 · ${emp.evidence.length} 条）</div>
      <div class="item-list">${emp.evidence.map((e) =>
        `<div class="item-card"><span class="evi-count">${esc(e.source_label)}</span><br>${esc(e.text.length > 120 ? e.text.slice(0, 120) + "…" : e.text)}</div>`).join("")}</div>
    </div>`;
  $("#empDrawer").classList.remove("hidden");
  $("#empDrawer").classList.add("open");
  requestAnimationFrame(() => $$(".bar-fill", $("#drawerBody")).forEach((b) => { b.style.width = b.dataset.w + "%"; }));
}

function kv(k, v) {
  return `<div class="kv"><div class="k">${esc(k)}</div><div class="v">${esc(v || "—")}</div></div>`;
}

function closeDrawer() { $("#empDrawer").classList.add("hidden"); }
$("#drawerClose").addEventListener("click", closeDrawer);
$("#empDrawer").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeDrawer(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeTrace(); closeDrawer(); }
});

/* ── 视图切换 ── */
$$(".nav-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".nav-tab").forEach((t) => t.classList.toggle("active", t === tab));
    $$(".view").forEach((v) => v.classList.remove("active"));
    $(`#view-${tab.dataset.view}`).classList.add("active");
    $$(".reveal", $(`#view-${tab.dataset.view}`)).forEach((el) => io.observe(el));
  });
});

init();
