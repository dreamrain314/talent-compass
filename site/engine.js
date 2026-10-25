/* Talent Compass 静态站 · JS 轻量覆盖引擎（与 utils/coverage_engine.py 对齐）
 * 词典/等价表/参数全部来自 data/engine_config.json（Python 导出，零硬编码）
 * 与 Python 全引擎的已知差异：无 embedding 召回（仅词法通道）、无语义桥——
 * 官方数字见 presets.json（Python 引擎预计算）。 */
"use strict";

const GATE_RE = /学历|年及以上|年以上.{0,4}经验|司龄|年限|等相关专业/;
const PREFIX_RE = /^(熟悉|掌握|精通|具备|具有|了解|能够|能|会|熟练使用|熟练掌握|承担|参与|负责|主导|组织|配合|协助|跟进|跟踪|推动|编写|收集|维护)+/;
const TAIL_PREF_RE = /(者)?优先$/;
const PAREN_RE = /[（(]([^（）()]*)[)）]/g;
const STATE_MARKERS = ["学习中", "计划中", "拟参加", "即将参加", "准备参加", "报名"];
const NEG_MARKERS = ["未参与", "没有相关", "不具备相关", "无相关经验", "未接触"];
const VERB_HEADS = ["熟悉", "掌握", "具备", "具有", "负责", "主导", "参与", "承担", "了解", "输出", "使用", "持有", "能够", "开展", "完成"];
const REL_VALUES = { equivalent: 1.0, direct_support: 1.0, state_different: 0.5, relevant_only: 0.0, contradiction: 0.0 };
const ENUM_DENG_RE = /([^，。；、（）()；;\s等]{2,8})、([^，。；、（）()；;\s等]{2,8})等/g;

const Engine = {
  CFG: null,
  loadConfig(cfg) { Engine.CFG = cfg; },

  norm(s) { return String(s ?? "").toLowerCase().replace(/\s+/g, ""); },

  splitClauses(item) {
    const parts = item.split(/[，；;]/).map((x) => x.trim()).filter(Boolean);
    const kept = parts.filter((p) => Engine.norm(p).length >= 4);
    return kept.length ? kept : [item];
  },

  stripLead(s) {
    const t = s.replace(PREFIX_RE, "");
    return Engine.norm(t).length ? t : s;
  },

  duhaoInstances(item) {
    const out = [];
    ENUM_DENG_RE.lastIndex = 0;
    let m;
    while ((m = ENUM_DENG_RE.exec(item))) {
      const segs = [Engine.stripLead(m[1]).trim(), Engine.stripLead(m[2]).trim()];
      if (segs.every((s) => s.length >= 2 && s.length <= 8 && !VERB_HEADS.some((v) => s.includes(v)))) {
        segs.forEach((s) => { if (!out.includes(s)) out.push(s); });
      }
      if (out.length) return out;
    }
    for (const clause of item.split(/[，。；]/)) {
      if ((clause.match(/、/g) || []).length >= 2) {
        const segs = clause.split(/、/).map((s) => Engine.stripLead(s.trim())).filter(Boolean);
        const clean = segs.filter((s) => s.length >= 2 && s.length <= 8 && !VERB_HEADS.some((v) => s.includes(v)));
        if (clean.length === segs.length && clean.length >= 3) clean.forEach((s) => { if (!out.includes(s)) out.push(s); });
      }
    }
    return out;
  },

  extractRequirements(job, clauseSplit = true) {
    const reqs = [], seen = new Set();
    const raw = [...(job.requirements || []), ...(job.responsibilities || [])].map(String).filter(Boolean);
    raw.forEach((item, idx) => {
      const subs = clauseSplit ? Engine.splitClauses(item) : [item];
      subs.forEach((sub, si) => {
        if (GATE_RE.test(sub)) return;
        const instances = [];
        let m; PAREN_RE.lastIndex = 0;
        while ((m = PAREN_RE.exec(sub))) {
          m[1].split(/[/、，,]/).forEach((p) => { const t = p.trim(); if (t) instances.push(t); });
        }
        let head = sub.replace(PAREN_RE, "").replace(/\s+/g, "");
        head = head.replace(PREFIX_RE, "") || head;
        head = head.replace(/[；;。.，, ]+$/, "");
        head = head.replace(TAIL_PREF_RE, "") || head;
        if (!head) return;
        let inst = [...instances];
        if (!inst.length && (head.match(/\//g) || []).length >= 1) {
          const segs = head.split("/").map((s) => s.trim()).filter((s) => s.length >= 2);
          if (segs.length >= 2) inst = segs;
        }
        if (!inst.length) inst = Engine.duhaoInstances(sub);
        const kind = sub.includes("优先") ? "preferred" : "necessary";
        const key = Engine.norm(head);
        if (seen.has(key)) return;
        seen.add(key);
        const base = `R${String(idx + 1).padStart(2, "0")}`;
        reqs.push({
          rid: subs.length === 1 ? base : `${base}-${String.fromCharCode(97 + si)}`,
          text: sub, head, instances: inst, kind,
          weight: Engine.CFG.params.w_must, either_ok: inst.length > 0,
        });
      });
    });
    return reqs;
  },

  requirementType(req) {
    const h = Engine.norm(req.head);
    const inst = Engine.norm(req.instances.join(""));
    const L = Engine.CFG.lexicons;
    if (L.professional_strong.some((w) => h.includes(w))) return "professional";
    if (L.professional_strong.some((w) => inst.includes(w))) return "professional";
    if (L.professional_weak.some((w) => inst.includes(w))) return "professional";
    if (L.behavior.some((w) => h.includes(w))) return "behavioral";
    return "professional";
  },

  headCoreTerms(head) {
    const h = Engine.norm(head);
    return h && h.length <= 6 ? [h] : [];
  },

  headLookupKeys(req) {
    const keys = [...Engine.headCoreTerms(req.head), ...req.instances.map((t) => Engine.norm(t)).filter(Boolean)];
    const h = Engine.norm(req.head);
    if (h.length > 6) {
      req.head.split(/[，。；、]/).forEach((seg) => {
        const n = Engine.norm(Engine.stripLead(seg.trim()));
        if (n.length >= 2 && !keys.includes(n)) keys.push(n);
      });
    }
    return keys;
  },

  lexicalScore(req, text) {
    const grams = (s) => {
      const t = Engine.norm(s); const g = new Set();
      for (let i = 0; i < t.length - 1; i++) g.add(t.slice(i, i + 2));
      return t.length > 1 ? g : new Set([t]);
    };
    const a = grams(req.head + req.instances.join(""));
    const b = grams(text);
    let inter = 0; a.forEach((x) => { if (b.has(x)) inter++; });
    return a.size && b.size ? (2 * inter) / (a.size + b.size) : 0;
  },

  recallCandidates(req, chunks) {
    const scored = chunks.map((c) => ({ c, lex: Engine.lexicalScore(req, c.text) }));
    scored.sort((x, y) => y.lex - x.lex);
    const top = scored.slice(0, 2).map((s) => s.c);
    // 字面包含快速通道：head（≥6 字）逐字出现的 chunk 必入候选且不受 top-k
    // 截断（Dice 对长 chunk 系统性不利，逐字包含是最强证据）
    const h = Engine.norm(req.head);
    const contain = [];
    if (h.length >= 6) {
      for (const c of chunks) {
        if (Engine.norm(c.text).includes(h) && !top.includes(c)) contain.push(c);
      }
    }
    return [...top.slice(0, Engine.CFG.params.recall_k), ...contain];
  },

  classifyRelation(req, chunk) {
    const textN = Engine.norm(chunk.text);
    const termNorms = [Engine.norm(req.head), ...req.instances.map((t) => Engine.norm(t))].filter(Boolean);
    const cores = Engine.headCoreTerms(req.head);
    const hits = termNorms.filter((t) => textN.includes(t));
    const coreHits = cores.filter((t) => textN.includes(t));
    const termHit = !!(hits.length || coreHits.length);
    const isState = STATE_MARKERS.some((mk) => chunk.text.includes(mk));
    const isNeg = NEG_MARKERS.some((mk) => chunk.text.includes(mk));
    if (termHit && isNeg) return { relation: "contradiction", value: 0, hit_terms: hits.concat(coreHits), note: "记录含明确否定标记" };
    if (termHit && isState) return { relation: "state_different", value: REL_VALUES.state_different, hit_terms: hits.concat(coreHits), note: "计划/学习中，非已完成" };
    const eq = Engine.CFG.equivalences;
    const deduct = new Set(Engine.CFG.deduct.map((d) => d.join("→")));
    const lookup = Engine.headLookupKeys(req);
    let eqPairs = [];
    for (const t of lookup) for (const v of (eq[t] || [])) if (v && textN.includes(v)) eqPairs.push([t, v]);
    if (!eqPairs.length) {
      const reqFull = Engine.norm(req.text + req.head + req.instances.join(""));
      for (const k of Object.keys(eq)) {
        if (k.length >= 2 && reqFull.includes(k)) for (const v of eq[k]) if (v && textN.includes(v)) eqPairs.push([k, v]);
      }
    }
    if (eqPairs.length) {
      const hitDeduct = eqPairs.some(([k, v]) => deduct.has(`${k}→${v}`));
      return { relation: "equivalent", value: hitDeduct ? Engine.CFG.params.deduction_value : 1.0,
               hit_terms: eqPairs.map((p) => p[1]),
               note: hitDeduct ? "等价表命中（D组受众错位 0.8）" : "经核验等价表命中（与字面同档）" };
    }
    if (termHit) return { relation: "direct_support", value: 1.0, hit_terms: hits.concat(coreHits), note: "实例/核心词命中（有向支持）" };
    return { relation: "relevant_only", value: 0, hit_terms: [], note: "主题相邻但未检出支持性证据" };
  },

  expandAtomic(reqs) {
    const splits = Engine.CFG.atomic_splits;
    if (!splits || !Object.keys(splits).length) return reqs;
    const out = [];
    for (const r of reqs) {
      const h = Engine.norm(r.head);
      const compound = Object.keys(splits).find((c) => c && h.includes(c));
      if (!compound) { out.push(r); continue; }
      const atoms = splits[compound];
      atoms.forEach((a, i) => out.push({ ...r, rid: `${r.rid}-${String.fromCharCode(97 + i)}`, text: a, head: a, instances: [], either_ok: true, weight: r.weight / atoms.length }));
    }
    return out;
  },

  potentialScore(emp) {
    const gm = { A: 4, B: 3, C: 2, D: 1 };
    const grades = (emp.performance || []).map((x) => gm[x.grade]).filter((x) => x != null);
    const tc = (emp.training || []).length;
    if (!grades.length && !tc) return 0.5;
    const avg = grades.length ? (grades.reduce((a, b) => a + b, 0) / grades.length - 1) / 3 : 0.5;
    const trend = grades.length >= 2 ? (grades[grades.length - 1] - grades[0] + 3) / 6 : 0.5;
    const train = Math.min(tc, 5) / 5;
    return 0.5 * avg + 0.3 * trend + 0.2 * train;
  },

  score(jobType, job, employees) {
    let reqs = Engine.expandAtomic(Engine.extractRequirements(job));
    reqs.forEach((r) => { r.rtype = Engine.requirementType(r); });
    const w = Engine.CFG.matrix[(jobType || "").trim()] || Engine.CFG.matrix._default;
    const profMust = reqs.filter((r) => r.rtype === "professional" && r.kind === "necessary");
    const behavMust = reqs.filter((r) => r.rtype === "behavioral" && r.kind === "necessary");
    const preferred = reqs.filter((r) => r.kind === "preferred");
    const nMust = profMust.length + behavMust.length;

    const results = employees.map((emp) => {
      const reqResults = {};
      for (const req of reqs) {
        const cands = Engine.recallCandidates(req, emp.chunks);
        let best = null, bestKey = -1;
        for (const c of cands) {
          const cls = Engine.classifyRelation(req, c);
          const key = cls.value * 10 + (cls.relation === "contradiction" ? 1 : 0);
          if (key > bestKey) { best = { cls, chunk: c }; bestKey = key; }
          if (cls.value >= 1.0) break;
        }
        reqResults[req.rid] = {
          v: best ? best.cls.value : 0,
          relation: best ? best.cls.relation : "no_candidate",
          note: best ? best.cls.note : "无候选证据",
          evidence: best ? [{ source: best.chunk.source, text: best.chunk.text }] : [],
        };
      }
      const pool = (list) => list.length
        ? list.reduce((s, r) => s + r.weight * reqResults[r.rid].v, 0) / list.reduce((s, r) => s + r.weight, 0)
        : null;
      const sProfRaw = pool(profMust), sBehavRaw = pool(behavMust);
      const sProf = sProfRaw === null ? 0.5 : sProfRaw;
      const sBehav = sBehavRaw === null ? 0.5 : sBehavRaw;
      const bonus = preferred.length
        ? (Engine.CFG.params.preferred_k * preferred.reduce((s, r) => s + reqResults[r.rid].v, 0) / Math.max(1, nMust))
        : 0;
      const p = Engine.potentialScore(emp);
      let total = w[0] * sProf + w[1] * sBehav + w[2] * p + bonus;
      const gateRids = profMust.filter((r) => reqResults[r.rid].v <= 1e-9).map((r) => r.rid);
      const coef = Math.max(0, 1 - Engine.CFG.params.gate_step * gateRids.length);
      if (gateRids.length) total *= coef;
      return {
        id: emp.id, name: emp.name, position: emp.position,
        total: Math.round(total * 100) / 100,
        s_prof: Math.round(sProf * 10000) / 10000,
        s_behav: Math.round(sBehav * 10000) / 10000,
        p: Math.round(p * 10000) / 10000,
        bonus: Math.round(bonus * 10000) / 10000,
        gate: gateRids.length ? { k: gateRids.length, coef: Math.round(coef * 10000) / 10000 } : null,
        requirements: reqResults, reqs,
      };
    });
    results.sort((a, b) => b.total - a.total || (a.id < b.id ? -1 : 1));
    return { w, results };
  },
};

if (typeof module !== "undefined") module.exports = { Engine };
else globalThis.Engine = Engine;
