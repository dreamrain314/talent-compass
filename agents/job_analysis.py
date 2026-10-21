"""Agent③' 岗位要求解析（M2，向量直配匹配层上游）。

职责：岗位描述（职责/任职要求文本）→ 结构化岗位画像 JSON：
- hard_requirements：H0/H1 硬条件（学历下限/年限下限/必备证书），供匹配层硬闸门
- skill_requirements：T0/T1 技能要求项 [{name, detail}]，供语义检索 query 构造
- soft_requirements：T2/T3 行为/潜力偏好项

双路径（D6 确定性降级）：
- offline / LLM 失败 → 离线确定性抽取：正则抓硬条件 + 标签库 corpus（94 项，
  含 T0 注册表别名）关键词扫描出技能/软性要求项——即竞品三层栈 L1 字面层的等价物
- LLM（温度 0）→ 结构化解析富化；解析结果仅做结构校验，非法即回退离线结果

零评分原则：本 Agent 只"理解与结构化"，不产生任何匹配分数（竞品"零 LLM 评分"
纪律的移植：LLM 管理解，公式管评分）。

消费者：scripts/run_matching.py（M5 编排）、scripts/blind_test.py（M4 盲测）。
"""

from __future__ import annotations

import re

import config
from agents.base_agent import BaseAgent
from utils.llm_client import call_llm_json
from utils.logger import setup_logger
from utils.label_embedding import load_label_corpus

logger = setup_logger()

__all__ = ["JobAnalysis"]

# 学历序数（H 闸门比较用；与开题报告口径一致）
EDUCATION_ORDINAL = {"大专": 1, "本科": 2, "硕士": 3, "研究生": 3, "博士": 4}

_EDU_PATTERN = re.compile(r"(大专|本科|硕士|研究生|博士)")
_YEARS_PATTERN = re.compile(r"([0-9]+|[一二两三四五六七八九十]+)\s*年[以上及]*.*?经验")
_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# 证书线索词（在 JD 文本中命中即记为必备/优先证书）
_CERT_HINTS = [
    "PMP", "项目管理师", "会计师", "法律职业资格", "CPA", "CFA",
    "注册工程师", "中级职称", "高级职称", "CET-6", "英语六级",
]

_JOB_ANALYSIS_SYSTEM_PROMPT = (
    "你是资深 HR 岗位分析师。从给定的招聘职位描述中抽取结构化岗位画像。"
    "只做理解与结构化，不做任何打分或候选人猜测。"
    "输出 JSON，格式："
    '{"hard_requirements": {"education_min": "大专|本科|硕士|博士 或空串", '
    '"years_min": 整数或null, "certificates": ["必备/优先证书名"]}, '
    '"skill_requirements": [{"name": "技能/领域名(≤8字)", "detail": "具体要求一句话"}], '
    '"soft_requirements": [{"name": "行为/潜力特质(≤8字)", "detail": "一句话"}], '
    '"summary": "岗位一句话概括"}。'
    "skill_requirements 列出 5-12 条核心技能要求（按重要性排序），"
    "soft_requirements 列出 0-4 条软性偏好。"
)

_MAX_SKILL_REQS = 12
_MAX_SOFT_REQS = 4


def _cn_to_int(s: str) -> int | None:
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s in _CN_NUM:
        return _CN_NUM[s]
    if s == "十一":
        return 11
    if s == "十二":
        return 12
    return None


def _offline_extract(job: dict, corpus: list[dict]) -> dict:
    """离线确定性抽取（零 LLM）：正则硬条件 + corpus 关键词扫描。"""
    resp = "\n".join(str(x) for x in (job.get("responsibilities") or []))
    reqs = "\n".join(str(x) for x in (job.get("requirements") or []))
    text = f"{job.get('title', '')}\n{resp}\n{reqs}"

    # ── 硬条件（正则）──
    edu_m = _EDU_PATTERN.search(reqs)
    years_min = None
    years_m = _YEARS_PATTERN.search(reqs)
    if years_m:
        years_min = _cn_to_int(years_m.group(1))
    certs = [c for c in _CERT_HINTS if c.lower() in text.lower()]
    hard = {
        "education_min": edu_m.group(1) if edu_m else "",
        "years_min": years_min,
        "certificates": certs,
    }

    # ── 技能/软性要求（corpus 名称+关键词字面扫描，L1 字面层等价物）──
    scored: list[dict] = []
    for item in corpus:
        name = item.get("name", "")
        if not name:
            continue
        score = 0
        matched: list[str] = []
        if name in text:
            score += 3
            matched.append(name)
        for kw in item.get("keywords", []) or []:
            if kw and kw in text:
                score += 1
                matched.append(kw)
            if score > 0:
                detail = "、".join(dict.fromkeys(matched)) if matched else item.get("definition", "")[:40]
                scored.append({
                    "name": name,
                    "detail": detail,
                    "tier": item.get("tier", ""),
                    "_score": score,
                })
    scored.sort(key=lambda x: -x["_score"])
    # 同名去重（保留最高分项）：标签库与 T0 注册表可能产出同名项，
    # 重复项会撑大 T0 分母并让字面层失去区分度（2026-10-21 修复）
    dedup: dict[str, dict] = {}
    for s in scored:
        dedup.setdefault(s["name"], s)
    scored = list(dedup.values())

    skill_reqs = [
        {"name": s["name"], "detail": s["detail"]}
        for s in scored
        if s["tier"].startswith("T1") or s["tier"] == "T0"
    ][:_MAX_SKILL_REQS]
    soft_reqs = [
        {"name": s["name"], "detail": s["detail"]}
        for s in scored
        if s["tier"] in ("T2_行为能力", "T3_发展潜力")
    ][:_MAX_SOFT_REQS]

    return {
        "hard_requirements": hard,
        "skill_requirements": skill_reqs,
        "soft_requirements": soft_reqs,
        "summary": str(job.get("title", "")),
    }


def _validate_llm_profile(content) -> dict | None:
    """校验 LLM 解析结果结构（非法返回 None 触发回退，不抛异常）。"""
    if not isinstance(content, dict):
        return None
    hard = content.get("hard_requirements")
    skills = content.get("skill_requirements")
    if not isinstance(hard, dict) or not isinstance(skills, list) or not skills:
        return None
    norm_skills = []
    for s in skills:
        if isinstance(s, dict) and s.get("name"):
            norm_skills.append({
                "name": str(s["name"])[:20],
                "detail": str(s.get("detail", ""))[:120],
            })
    if not norm_skills:
        return None
    norm_soft = []
    for s in content.get("soft_requirements") or []:
        if isinstance(s, dict) and s.get("name"):
            norm_soft.append({
                "name": str(s["name"])[:20],
                "detail": str(s.get("detail", ""))[:120],
            })
    years_min = hard.get("years_min")
    if not isinstance(years_min, int) or years_min < 0:
        years_min = None
    certs = [str(c) for c in (hard.get("certificates") or []) if c]
    return {
        "hard_requirements": {
            "education_min": str(hard.get("education_min", "") or ""),
            "years_min": years_min,
            "certificates": certs,
        },
        "skill_requirements": norm_skills[:_MAX_SKILL_REQS],
        "soft_requirements": norm_soft[:_MAX_SOFT_REQS],
        "summary": str(content.get("summary", ""))[:120],
    }


def build_queries(profile: dict, corpus: list[dict]) -> list[str]:
    """技能要求 → 检索 query 文本（用 corpus definition 富化，提升向量分辨率）。"""
    by_name = {c.get("name", ""): c for c in corpus if c.get("name")}
    queries: list[str] = []
    for s in profile.get("skill_requirements", []):
        name = s.get("name", "")
        detail = s.get("detail", "")
        lib_def = ""
        item = by_name.get(name)
        if item:
            lib_def = item.get("definition", "") or ""
        parts = [name]
        if lib_def:
            parts.append(lib_def)
        if detail and detail not in lib_def:
            parts.append(detail)
        queries.append("：".join([parts[0], "；".join(parts[1:])]) if len(parts) > 1 else name)
    return queries


class JobAnalysis(BaseAgent):
    agent_name = "job_analysis"
    agent_version = "1.0.0"
    timeout_seconds = 180

    def validate_input(self, data: dict) -> bool:
        if not isinstance(data, dict):
            return False
        job = data.get("job")
        return isinstance(job, dict) and bool(job.get("title"))

    def execute(self, data: dict, context: dict) -> dict:
        job = data["job"]
        corpus = load_label_corpus()

        # 路径 1：离线确定性抽取（始终先算，作为降级底座）
        profile = _offline_extract(job, corpus)
        parse_source = "offline"

        # 路径 2：LLM 结构化解析（offline 模式或取消时跳过；失败回退离线结果）
        if not config.is_offline_mode() and not self._check_cancel(context):
            jd_text = self._render_jd_text(job)
            try:
                result = call_llm_json(
                    prompt=jd_text,
                    system_prompt=_JOB_ANALYSIS_SYSTEM_PROMPT,
                    temperature=0.0,
                    max_tokens=2048,
                    timeout=config.SUMMARY_LLM_TIMEOUT,
                )
                content = result.get("content")
                if result.get("error") is None and content is not None:
                    validated = _validate_llm_profile(content)
                    if validated is not None:
                        profile = validated
                        parse_source = "llm"
                    else:
                        logger.warning(
                            "job_analysis LLM 解析结构非法，回退离线抽取",
                            extra={"trace_id": context.get("trace_id", "-"),
                                   "agent_name": self.agent_name},
                        )
            except Exception as exc:  # D6：确定性回退，零重试
                logger.warning(
                    "job_analysis LLM 调用失败，回退离线抽取: %s", exc,
                    extra={"trace_id": context.get("trace_id", "-"),
                           "agent_name": self.agent_name},
                )

        job_profile = {
            "job_id": str(job.get("job_id", "")),
            "title": str(job.get("title", "")),
            "company": str(job.get("company", "")),
            "department": str(job.get("department", "")),
            "hard_requirements": profile["hard_requirements"],
            "skill_requirements": profile["skill_requirements"],
            "soft_requirements": profile["soft_requirements"],
            "summary": profile.get("summary", ""),
            "queries": build_queries(profile, corpus),
            "parse_source": parse_source,
        }

        return {
            "status": "success",
            "data": {
                "job_profile": job_profile,
                # 透传 employees 给下游 MatchingAgent（PipelineRunner 内存直传）
                "employees": data.get("employees") or [],
            },
            "metadata": {
                "data_lineage": {
                    "model": parse_source,
                    "timestamp": "",
                    "audit_status": "verified",
                },
            },
        }

    @staticmethod
    def _render_jd_text(job: dict) -> str:
        resp = "\n".join(f"- {x}" for x in (job.get("responsibilities") or []))
        reqs = "\n".join(f"- {x}" for x in (job.get("requirements") or []))
        meta = (
            f"职位：{job.get('title', '')}（{job.get('company', '')}"
            f" {job.get('department', '')}）"
        )
        return f"{meta}\n\n工作职责：\n{resp}\n\n任职要求：\n{reqs}"

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "required": ["job"],
            "properties": {
                "job": {
                    "type": "object",
                    "required": ["title"],
                    "properties": {
                        "job_id": {"type": "string"},
                        "title": {"type": "string"},
                        "responsibilities": {"type": "array", "items": {"type": "string"}},
                        "requirements": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "employees": {"type": "array"},
            },
        }

    def get_output_schema(self) -> dict:
        return {
            "type": "object",
            "required": ["job_profile", "employees"],
            "properties": {
                "job_profile": {
                    "type": "object",
                    "required": ["job_id", "title", "hard_requirements",
                                 "skill_requirements", "queries", "parse_source"],
                },
                "employees": {"type": "array"},
            },
        }
