/* UI 层：依赖 engine.js 的全局 Engine */
/* ───────────────────────── UI ───────────────────────── */
const App = (() => {
  let EMP = [], PRESETS = [], META = {};
  const $ = (s) => document.querySelector(s);
  const el = (t, cls, html) => { const e = document.createElement(t); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  async function boot() {
    const [cfg, emp, presets, meta] = await Promise.all([
      fetch("data/engine_config.json").then((r) => r.json()),
      fetch("data/employees.json").then((r) => r.json()),
      fetch("data/presets.json").then((r) => r.json()),
      fetch("data/meta.json").then((r) => r.json()),
    ]);
    Engine.loadConfig(cfg);
    EMP = emp; PRESETS = presets; META = meta;
    $("#meta").textContent = `${META.pool}｜引擎 ${META.engine}｜commit ${META.commit}｜快照 ${META.generated.slice(0, 10)}`;
    renderPresetChips();
    bindEvents();
  }

  function renderPresetChips() {
    const box = $("#presetChips"); box.innerHTML = "";
    PRESETS.forEach((p) => {
      const chip = el("button", "chip", esc(`${p.job_id.replace("JOB_", "")} ${p.title}`));
      chip.onclick = () => { $("#jdBox").value = presetToJD(p); runMatch(p.job_id); };
      box.appendChild(chip);
    });
  }

  function presetToJD(p) {
    const jd = p.jd || {};
    return [...(jd.requirements || []), ...(jd.responsibilities || [])].join("\n");
  }

  async function runMatch(presetId) {
    const jdText = $("#jdBox").value.trim();
    if (!jdText) return;
    $("#runStatus").textContent = "匹配中…";
    await new Promise((r) => setTimeout(r, 20));
    let job = null;
    if (presetId) {
      const p = PRESETS.find((x) => x.job_id === presetId);
      job = p ? parseJDText(jdText, p.job_type) : parseJDText(jdText, "");
    } else job = parseJDText(jdText, "");
    const t0 = performance.now();
    const { w, results } = Engine.score(job.job_type, job, EMP);
    const ms = Math.round(performance.now() - t0);
    $("#runStatus").textContent = `完成（${ms} ms，轻量引擎：词法召回+等价表）`;
    renderResults(w, results, presetId);
  }

  function parseJDText(text, jobType) {
    const lines = text.split(/\n+/).map((s) => s.trim()).filter(Boolean);
    return { job_type: jobType || guessJobType(text), requirements: lines, responsibilities: [] };
  }

  function guessJobType(text) {
    if (/开发|工程师|算法|架构|嵌入|大数据|测试/.test(text)) return "技术类";
    if (/经理|主管|人力|财务|审计|行政|职能/.test(text)) return "职能类";
    if (/销售|市场|商务|客户/.test(text)) return "业务类";
    if (/设计|产品|创意|策划/.test(text)) return "创意类";
    return "技术类";
  }

  const STATUS = { equivalent: "已支持（等价）", direct_support: "已支持", state_different: "部分（状态存疑）", relevant_only: "未证实", contradiction: "冲突标记", no_candidate: "未证实（无候选）" };

  function renderResults(w, results, presetId) {
    const box = $("#results"); box.innerHTML = "";
    box.appendChild(el("div", "wline", `权重矩阵（${results[0]?.reqs ? "" : ""}专业/行为/潜力）：${w[0]} / ${w[1]} / ${w[2]}`));
    const official = presetId ? PRESETS.find((p) => p.job_id === presetId) : null;
    if (official) box.appendChild(el("div", "official", `官方口径（Python 引擎，含语义召回+语义桥）Top5：${official.top.slice(0, 5).map((t, i) => `${i + 1}.${t.name}(${t.total})`).join("　")}`));
    results.slice(0, 10).forEach((r, i) => {
      const card = el("div", "card");
      const gate = r.gate ? `<span class="gate">专业闸门 k=${r.gate.k} ×${r.gate.coef}</span>` : "";
      card.appendChild(el("div", "cardhead",
        `<span class="rank">#${i + 1}</span><b>${esc(r.name)}</b><span class="pos">${esc(r.position)}</span>
         <span class="total">${r.total}</span>${gate}`));
      card.appendChild(el("div", "bars",
        `<span>专业 ${r.s_prof}</span><span>行为 ${r.s_behav}</span><span>潜力 ${r.p}</span><span>加分 ${r.bonus}</span>`));
      const matrix = el("div", "matrix");
      r.reqs.forEach((req) => {
        const rr = r.requirements[req.rid];
        const ev = rr.evidence[0];
        matrix.appendChild(el("div", "mrow",
          `<span class="tag ${rr.v >= 1 ? "ok" : rr.v > 0 ? "half" : "no"}">${STATUS[rr.relation] || rr.relation}</span>
           <span class="req">${esc(req.head.slice(0, 30))}</span>
           <span class="ev">${ev ? esc(ev.text.slice(0, 44)) : "—"}</span>`));
      });
      const toggle = el("button", "fold", "证据矩阵");
      const mwrap = el("div", "mwrap"); mwrap.appendChild(matrix); mwrap.style.display = "none";
      toggle.onclick = () => { mwrap.style.display = mwrap.style.display === "none" ? "block" : "none"; };
      card.appendChild(toggle); card.appendChild(mwrap);
      box.appendChild(card);
    });
  }

  function renderEmployees(q) {
    const box = $("#empGrid"); box.innerHTML = "";
    EMP.filter((e) => !q || e.name.includes(q) || e.position.includes(q) || e.id.includes(q.toUpperCase())).forEach((e) => {
      const c = el("div", "empcard",
        `<b>${esc(e.name)}</b><span>${esc(e.position)}</span><span class="lvl">${esc(e.level)}｜${e.years}年</span>`);
      c.onclick = () => renderProfile(e);
      box.appendChild(c);
    });
  }

  function renderProfile(e) {
    const drawer = $("#drawer");
    const perf = (e.performance || []).map((p) => `${p.year} ${p.grade}：${esc((p.comment || "").slice(0, 40))}`).join("<br>");
    const projs = (e.projects || []).map((p) => `「${esc(p.project_name)}」${esc(p.role)}｜${esc((p.tools || []).join("/"))}`).join("<br>");
    const trains = (e.training || []).map((t) => `${esc(t.course_name)}（${esc(t.status)}）`).join("　");
    const s360 = Object.entries(e.scores_360 || {}).map(([k, v]) => `${k} ${v}`).join("　");
    drawer.innerHTML = `<div class="phead"><b>${esc(e.name)}</b><span>${esc(e.position)}｜${esc(e.level)}｜${esc(e.education)} ${esc(e.major)}</span>
      <span>证书：${esc(e.certificates || "无")}</span><button onclick="document.getElementById('drawer').classList.remove('open')">关闭</button></div>
      <div class="psec"><h4>绩效轨迹</h4>${perf || "—"}</div>
      <div class="psec"><h4>项目</h4>${projs || "—"}</div>
      <div class="psec"><h4>培训</h4>${trains || "—"}</div>
      <div class="psec"><h4>360 五维</h4>${s360 || "—"}</div>
      <div class="psec"><h4>证据切片（引擎实际检索的单位）</h4>${e.chunks.map((c) => `<div class="chunk">[${esc(c.source)}] ${esc(c.text.slice(0, 70))}</div>`).join("")}</div>`;
    drawer.classList.add("open");
  }

  function bindEvents() {
    $("#runBtn").onclick = () => runMatch(null);
    $("#empTab").onclick = () => { $("#matchView").style.display = "none"; $("#empView").style.display = "block"; renderEmployees($("#empSearch").value); };
    $("#matchTab").onclick = () => { $("#matchView").style.display = "block"; $("#empView").style.display = "none"; };
    $("#empSearch").oninput = (e) => renderEmployees(e.target.value);
  }

  return { boot };
})();
document.addEventListener("DOMContentLoaded", App.boot);
