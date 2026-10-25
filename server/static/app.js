/* Talent Compass 匹配工作台 — 前端交互（Round 3 覆盖引擎口径） */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

const STATE = {
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
    STATE.sourceLabels = state.source_labels;
    STATE.employees = empData.employees;
    STATE.jobs = jobData.jobs;

    $("#navMeta").textContent = `${state.n_employees} 人 · ${state.engine.split("（")[0]}`;
    $("#footModels").textContent = state.engine;
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
      const jt = $("#jobType");
      if (jt) jt.value = j.job_type || "技术类";
    });
  });
}

/* ── 匹配 ── */
$("#matchForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const payload = {
    title: $("#jobTitle").value.trim(),
    job_type: $("#jobType") ? $("#jobType").value : "技术类",
    responsibilities: $("#jobResp").value.split("\n").map((s) => s.trim()).filter(Boolean),
    requirements: $("#jobReq").value.split("\n").map((s) => s.trim()).filter(Boolean),
    top_k: +$("#topK").value,
    filters: {
      gender: $("#fltGender") ? $("#fltGender").value : "",
      education_min: $("#fltEdu") ? $("#fltEdu").value : "",
      major: $("#fltMajor") ? $("#fltMajor").value.trim() : "",
    },
  };
  if (!payload.responsibilities.length && !payload.requirements.length) {
    alert("请填写工作职责或任职要求（也可点选示例岗位）");
    return;
  }
  setLoading(true, "要求拆解 · 全员证据对齐 · 覆盖评分…");
  try {
    const t0 = performance.now();
    const res = await fetch("/api/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
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

const STATUS = {
  equivalent: "已支持（等价）", direct_support: "已支持",
  state_different: "部分（状态存疑）", relevant_only: "未证实",
  contradiction: "冲突标记", no_candidate: "未证实（无候选）",
};

function renderResults(data) {
  STATE.lastResults = data;
  $("#matchEmpty").classList.add("hidden");
  $("#matchResults").classList.remove("hidden");
  $("#resultJobTitle").textContent = `${data.job.title}（${data.job.job_type}）`;
  const s = data.summary;
  $("#resultStats").innerHTML = `
    <span class="stat-pill">候选 <b>${s.n_candidates}</b> 人</span>
    ${s.filtered_out ? `<span class="stat-pill" title="用户硬性条件过滤排除">硬性过滤排除 <b>${s.filtered_out}</b> 人</span>` : ""}
    <span class="stat-pill">要求 <b>${s.n_requirements}</b> 条（专业 ${s.n_prof} / 行为 ${s.n_behav} / 优先 ${s.n_pref}）</span>
    <span class="stat-pill">权重 W <b>${s.w_matrix.join("/")}</b></span>
    <span class="stat-pill">闸门触发 <b>${s.n_gate}</b> 人</span>
    <span class="stat-pill">耗时 <b>${s.duration_ms}</b>ms</span>`;

  const strip = $("#parsedStrip");
  strip.innerHTML = `
    <div class="p-label">引擎拆解的原子要求（专=硬技能 · 行=软实力；必须进覆盖分 / 优先进加分）</div>
    <div class="parsed-tags">
      ${(data.job.reqs || []).map((r) =>
        `<span class="ptag ${r.rtype === "behavioral" ? "hard" : ""}">${esc(r.head.slice(0, 16))}<i> ${r.rtype === "behavioral" ? "行" : "专"}${r.kind === "preferred" ? " · 优" : ""}</i></span>`).join("")}
    </div>`;

  const list = $("#cardList");
  list.innerHTML = "";
  data.candidates.forEach((c, i) => list.appendChild(renderCard(c, i)));
  $$(".reveal", $("#matchResults")).forEach((el) => io.observe(el));
}

function renderCard(c, idx) {
  const el = document.createElement("article");
  el.className = `cand bezel rank-${idx + 1}`;
  el.dataset.rank = idx + 1;
  const gate = c.gate
    ? `<span class="badge rejected" title="专业类必须项缺 ${c.gate.k} 项 → 总分 ×${c.gate.coef}">专业闸门 −${Math.round((1 - c.gate.coef) * 100)}%</span>` : "";
  const neutral = c.class_neutral ? `<span class="badge clickable" title="该类要求为空 → 按缺失层惯例取中性 0.5">${c.class_neutral[0] === "behavioral" ? "行为类空·中性" : "专业类空·中性"}</span>` : "";
  el.innerHTML = `
    <div class="cand-inner">
      <div class="cand-top">
        <div class="rank">${idx + 1}</div>
        <div class="cand-id">
          <div class="cand-name-row">
            <span class="cand-name">${esc(c.name || c.emp_id)}</span>
            <span class="cand-meta">${esc(c.emp_id)}</span>
            ${gate}${neutral}
          </div>
          <div class="emp-sub" style="margin-top:.35rem" data-emp="${esc(c.emp_id)}"></div>
        </div>
        <div class="score-box top-score" title="覆盖引擎总分 = W1·专业 + W2·行为 + W3·潜力 + 优先加分（闸门后）">
          <div class="score-num" data-target="${c.total}">0</div>
          <div class="score-sub">综合匹配 / 100</div>
        </div>
      </div>
      <div class="cand-body">
        <div class="score-box" style="padding:.9rem .6rem">
          ${barRow("t0", "专业覆盖", c.s_prof)}
          ${barRow("t1", "行为覆盖", c.s_behav)}
          ${barRow("t3", "发展潜力", c.p)}
          ${c.bonus > 0 ? `<div class="bar-row"><span class="bar-label">优先加分</span><span class="bar-val" style="margin-left:auto">+${c.bonus}</span></div>` : ""}
        </div>
        <div>
          <div class="reason">${coverageSummary(c)}</div>
          ${renderReqMatrix(c)}
        </div>
      </div>
    </div>`;
  const emp = STATE.employees.find((e) => e.employee_id === c.emp_id);
  if (emp) {
    $(".emp-sub", el).innerHTML =
      `<span class="basic-line">${esc(emp.gender || "—")} · ${emp.age ?? "—"} 岁 · 工龄 ${emp.years ?? "—"} 年 · ${esc(emp.major || "—")} · ${esc(emp.education || "—")} · ${esc(emp.political_status || "—")}</span>` +
      `<span class="pos-line">${esc(emp.position || "—")} · ${esc(emp.level || "—")}</span>`;
  }
  el.title = "双击查看完整档案";
  el.addEventListener("dblclick", () => openDrawer(c.emp_id));
  requestAnimationFrame(() => {
    const num = $(".score-num", el);
    countUp(num, parseFloat(num.dataset.target), 1);
    $$(".bar-fill", el).forEach((b) => { b.style.width = b.dataset.w + "%"; });
  });
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

function barRow(cls, label, val01) {
  const pct = Math.min(100, val01 * 100).toFixed(1);
  return `<div class="bar-row ${"b-" + cls}">
    <span class="bar-label">${label}</span>
    <div class="bar-track"><div class="bar-fill" data-w="${pct}"></div></div>
    <span class="bar-val">${pct}%</span>
  </div>`;
}

function coverageSummary(c) {
  const vals = Object.values(c.requirements);
  const full = vals.filter((r) => r.v >= 1.0).length;
  const partial = vals.filter((r) => r.v > 0 && r.v < 1.0).length;
  const miss = vals.length - full - partial;
  return `要求覆盖 <b>${full}</b> 支持 / ${partial} 部分 / <b>${miss}</b> 未证实（共 ${vals.length} 条，v=max 取最佳证据）`;
}

function renderReqMatrix(c) {
  const rows = Object.entries(c.requirements || {});
  if (!rows.length) return "";
  return `<div class="evi-wrap">
    <button type="button" class="evi-toggle"><span class="arr">▶</span> 证据矩阵 · ${rows.length} 项要求（点开逐条溯源）</button>
    <div class="evi-list">
      ${rows.map(([rid, rr], i) => {
        const e = (rr.evidence || [])[0];
        return `
        <div class="evi-item">
          <div class="evi-src">${esc(STATUS[rr.relation] || rr.relation)} · v=${rr.v}</div>
          <div class="evi-text">
            <span class="q">${esc(rr.note)}</span>
            ${e ? esc(e.text.length > 160 ? e.text.slice(0, 160) + "…" : e.text) : "（无候选证据）"}
          </div>
          <div>${e ? `<button type="button" class="trace-btn" data-emp="${esc(c.emp_id)}" data-evi="${i}">溯源 ↗</button>` : ""}</div>
        </div>`;
      }).join("")}
    </div>
  </div>`;
}

/* ── 溯源弹层 ── */
async function openTrace(cand, eviIdx) {
  const rows = Object.entries(cand.requirements || {});
  const [, rr] = rows[eviIdx] || [];
  const evi = (rr?.evidence || [])[0];
  if (!evi) return;
  $("#traceTitle").textContent = `证据溯源 · ${cand.name || cand.emp_id}`;
  $("#traceBody").innerHTML = `<div class="trace-q">支持状态：${esc(STATUS[rr.relation] || rr.relation)}（v=${rr.v}）</div>
    <div class="trace-block"><span class="trace-src">${esc(evi.source_label || evi.source)}</span>
      <div class="trace-text">${esc(evi.text)}</div>
      <div class="trace-full"><span class="fl">LOADING ORIGINAL…</span></div>
    </div>`;
  $("#traceModal").classList.remove("hidden");
  try {
    const res = await fetch(`/api/employees/${encodeURIComponent(cand.emp_id)}`);
    const emp = await res.json();
    const full = fullTextFor(emp, evi);
    $(".trace-full", $("#traceBody")).innerHTML =
      `<span class="fl">原始记录 · ${esc(evi.source_label || evi.source)}（完整）</span>${full}
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
      <div class="emp-name">${esc(e.name || e.employee_id)}<span class="emp-gender">${esc(e.gender || "—")}</span></div>
      <div class="emp-sub">${e.age ?? "—"} 岁 · 工龄 ${e.years ?? "—"} 年 · ${esc(e.education || "—")}</div>
      <div class="emp-sub">${esc(e.major || "—")} · ${esc(e.political_status || "—")}</div>
      <div class="emp-sub pos">${esc(e.position || "—")} · ${esc(e.level || "—")}</div>
      <div class="emp-trend">${trend || "<span style='color:var(--ink-faint);font-size:.7rem'>无绩效记录</span>"}</div>
      <div class="emp-foot"><span>${esc(e.job_sequence || "—")}</span><span>证据 ${e.n_evidence}</span></div>
    </div>`;
    el.title = "点击查看完整档案";
    el.addEventListener("click", () => openDrawer(e.employee_id));
    grid.appendChild(el);
  });
  if (!list.length) grid.innerHTML = "<p style='color:var(--ink-faint)'>无匹配员工</p>";
}
$("#empSearch").addEventListener("input", (e) => renderEmpGrid(e.target.value));

/* ── 员工档案抽屉 ── */
function profileBodyHTML(emp) {
  const s = emp.summary, st = emp.structured || {};
  const trend = (s.performance_trend || []).map((g) =>
    `<span class="trend-dot g${{ A: 4, B: 3, C: 2, D: 1 }[g] || 0}">${esc(g)}</span>`).join(" → ");
  const s360 = emp.scores_360 || {};
  const s360max = Math.max(1, ...Object.values(s360).map((v) => +v || 0), 5);
  return `
    <div class="sec"><div class="sec-title">基本信息</div>
      <div class="kv-grid">
        ${kv("岗位", st.current_position)}${kv("职级", st.current_level)}
        ${kv("性别", st.gender)}${kv("年龄", st.age != null ? st.age + " 岁" : "—")}
        ${kv("工龄", st.years_of_service != null ? st.years_of_service + " 年" : "—")}
        ${kv("学历", st.education)}${kv("专业", st.major)}${kv("政治面貌", st.political_status)}
        ${kv("序列", st.job_sequence)}${kv("证书", st.certificates)}
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
    <div class="sec"><div class="sec-title">项目摘要（全文）</div>
      <div class="item-card">${esc(emp.text_summaries?.project_summary || "（无）")}</div>
    </div>
    <div class="sec"><div class="sec-title">360 评价摘要（全文，按分句展开）</div>
      ${(emp.text_summaries?.evaluation_summary || "").split("；").filter(Boolean).map((s) =>
        `<div class="item-card">· ${esc(s)}</div>`).join("") || '<div class="item-card">（无）</div>'}
    </div>
    <div class="sec"><div class="sec-title">绩效摘要（全文）</div>
      <div class="item-card">${esc(emp.text_summaries?.performance_summary || "（无）")}</div>
    </div>
    <div class="sec"><div class="sec-title">证据切片（向量索引素材 · ${emp.evidence.length} 条 · 全文）</div>
      <div class="item-list">${emp.evidence.map((e) =>
        `<div class="item-card"><span class="evi-count">${esc(e.source_label)}</span><br>${esc(e.text)}</div>`).join("")}</div>
    </div>`;
}

async function openDrawer(empId) {
  const res = await fetch(`/api/employees/${encodeURIComponent(empId)}`);
  const emp = await res.json();
  $("#drawerTitle").innerHTML = `
    <span class="eyebrow">EMPLOYEE PROFILE</span>
    <h3 style="font-size:1.3rem;margin-top:.5rem">${esc(emp.summary.name || empId)}
      <span style="font-size:.78rem;color:var(--ink-faint);font-family:var(--mono)">${esc(empId)}</span></h3>`;
  $("#drawerBody").innerHTML = profileBodyHTML(emp);
  $("#cmpBtn")?.remove();
  const btn = document.createElement("button");
  btn.className = "icon-btn"; btn.id = "cmpBtn"; btn.title = "与筛选出的员工并排对比";
  btn.textContent = "⇄ 对比";
  btn.addEventListener("click", () => openCompare(empId, emp));
  document.querySelector(".drawer-head").appendChild(btn);
  $("#empDrawer").classList.remove("hidden");
  $("#empDrawer").classList.add("open");
  requestAnimationFrame(() => $$(".bar-fill", $("#drawerBody")).forEach((b) => { b.style.width = b.dataset.w + "%"; }));
}

function kv(k, v) {
  return `<div class="kv"><div class="k">${esc(k)}</div><div class="v">${esc(v || "—")}</div></div>`;
}

/* ── 档案对比（双栏独立滚动） ── */
async function openCompare(empId, empCached) {
  let empA = empCached;
  if (!empA) {
    const res = await fetch(`/api/employees/${encodeURIComponent(empId)}`);
    empA = await res.json();
  }
  const pool = (STATE.lastResults?.candidates || []).length
    ? STATE.lastResults.candidates.map((c) => ({ id: c.emp_id, name: c.name || c.emp_id, position: "" }))
    : STATE.employees.map((e) => ({ id: e.employee_id, name: e.name, position: e.position }));
  $("#cmpPicker").innerHTML = "<h4>筛选出的员工（点击选择）</h4>" + pool.map((p) =>
    `<div class="cmp-item" data-emp="${esc(p.id)}" data-name="${esc(p.name)}">
       <b>${esc(p.name)}</b><span>${esc(p.id)}${p.position ? " · " + esc(p.position) : ""}</span></div>`).join("");
  $("#cmpLeftHead").innerHTML = `<b>${esc(empA.summary.name || empId)}</b><span>原档案（独立滚动）</span>`;
  $("#cmpLeftBody").innerHTML = profileBodyHTML(empA);
  $("#cmpRightHead").innerHTML = `<span>右侧选择后显示对比档案</span>`;
  $("#cmpRightBody").innerHTML = `<div class="cmp-empty">← 从左侧选择要对比的员工</div>`;
  $$(".cmp-item", $("#cmpPicker")).forEach((item) => {
    item.addEventListener("click", async () => {
      $$(".cmp-item", $("#cmpPicker")).forEach((x) => x.classList.remove("sel"));
      item.classList.add("sel");
      const rid = item.dataset.emp;
      $("#cmpRightBody").innerHTML = '<div class="cmp-empty">加载中…</div>';
      const res2 = await fetch(`/api/employees/${encodeURIComponent(rid)}`);
      const empB = await res2.json();
      $("#cmpRightHead").innerHTML = `<b>${esc(empB.summary.name || rid)}</b><span>对比档案（独立滚动）</span>`;
      $("#cmpRightBody").innerHTML = profileBodyHTML(empB);
      $$(".bar-fill", $("#cmpRightBody")).forEach((b) => { b.style.width = b.dataset.w + "%"; });
    });
  });
  $("#cmpModal").classList.remove("hidden");
  requestAnimationFrame(() => $$(".bar-fill", $("#cmpLeftBody")).forEach((b) => { b.style.width = b.dataset.w + "%"; }));
}

function closeCompare() { $("#cmpModal").classList.add("hidden"); }
$("#cmpClose").addEventListener("click", closeCompare);
$("#cmpModal").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeCompare(); });

function closeDrawer() { $("#empDrawer").classList.add("hidden"); }
$("#drawerClose").addEventListener("click", closeDrawer);
$("#empDrawer").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeDrawer(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeTrace(); closeDrawer(); closeCompare(); }
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
