"""Agent② 画像生成（ProfileGeneration）。

Day 1 骨架（2026-07-27）：
- _adapt_input：Agent① 输出格式 → Agent② 内部格式
- validate_input：双格式兼容（Agent① 原始 structured / 适配后 raw）
- execute：Phase 0 加载 corpus，Phase 1 占位（Day 3 实现并行池+LLM+Embedding 验证）

Day 2（2026-07-28）：
- _llm_extract：单员工 LLM 抽取 T1/T2/T3 raw + 大五（offline 短路 + 确定性降级，D6/F7 防雪崩）
- 输出供 5 员工对比实验脚本（scripts/experiment_embedding_vs_llm.py）消费
- Day 3 execute 将串联 _llm_extract + verify_mapping + compute_t3_scores

Day 3 将实现：
- Phase 1 每员工线程：LLM 提取 → Embedding 验证/纠正 → T3 分数 → 证据锚点校验
- Phase 2 成长曲线 + 汇总摘要
- 员工级超时包装（PER_EMP_TIMEOUT）
- ThreadPoolExecutor(W=min(5, N))

依据：第二周开发指南 Day 2 Task 2.1 + 「多Agent协作完整行为逻辑与实现方法」步骤 2.1-2.9。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

import config
from agents.base_agent import BaseAgent
from utils import numpy_to_native
from utils.label_embedding import (
    ability_score_from_level,
    clamp_int,
    encode_labels,
    get_embedding_model,
    load_label_corpus,
)
from utils.label_matching import recall_top_k, rerank_label_llm, rerank_cross_encoder
from utils.llm_client import call_llm_json
from utils.t3_scorer import compute_t3_scores

logger = logging.getLogger(__name__)

__all__ = ["ProfileGeneration"]


class ProfileGeneration(BaseAgent):
    """Agent②：员工画像生成。"""

    agent_name = "ProfileGeneration"
    agent_version = "1.0"
    timeout_seconds = config.AGENT_PROFILE_TIMEOUT

    # ── 输入适配（Agent① → Agent② 内部格式）──

    def _adapt_input(self, data: dict) -> dict:
        """将 Agent① 输出格式转换为 Agent② 内部格式。

        转换规则：
        - Agent① structured → Agent② raw
        - Agent① text_summaries → Agent② summary
        - Agent① performance → Agent② performance_history
        - Agent① scores_360(扁平) + confidence_360 → Agent② scores_360{dimensions+confidence}
        - Agent① training 保留（含 status 字段，无 completion_date 时置 None）
        - 补充：name 从 structured 提取，employee_id 透传

        返回格式对称（C1）：{"employees": [...], "llm_stats": {...}}。
        """
        adapted = []
        for emp in data.get("employees", []) or []:
            # C3 守卫：emp 非 dict 跳过
            if not isinstance(emp, dict):
                continue
            structured = emp.get("structured") or {}
            if not isinstance(structured, dict):
                structured = {}
            adapted.append(
                {
                    "employee_id": emp.get("employee_id", ""),
                    "name": structured.get("name", ""),
                    "raw": {
                        "age": structured.get("age"),
                        "political_status": structured.get("political_status"),
                        "major": structured.get("major"),
                        "years_of_service": structured.get("years_of_service", 0),
                        "current_level": structured.get("current_level", ""),
                        "certificates": structured.get("certificates", ""),
                        "job_sequence": structured.get("job_sequence", ""),
                    },
                    "summary": emp.get("text_summaries") or {},
                    "scores_360": {
                        "dimensions": emp.get("scores_360") or {},
                        # 🔴 or 0.0：confidence_360 可能显式为 None（Agent① 无 360 数据时），
                        # dict.get(key, default) 在键存在且值为 None 时返回 None 而非 default
                        "confidence": emp.get("confidence_360") or 0.0,
                    },
                    "performance_history": emp.get("performance") or [],
                    "training": [
                        {
                            "course_name": t.get("course_name", "") if isinstance(t, dict) else "",
                            "completion_date": t.get("completion_date") if isinstance(t, dict) else None,
                            "status": t.get("status", "") if isinstance(t, dict) else "",
                            "score": t.get("score") if isinstance(t, dict) else None,
                        }
                        for t in (emp.get("training") or [])
                    ],
                }
            )
        return {"employees": adapted, "llm_stats": data.get("llm_stats") or {}}

    # ── 输入校验（双格式兼容）──

    def validate_input(self, data: dict) -> bool:
        """校验输入：兼容 Agent① 原始格式和适配后格式。

        - 格式 A（Agent① 原始）：employees[i] 含 structured 字段
        - 格式 B（适配后）：employees[i] 含 raw 字段
        - 空员工列表（len==0）合法 → True
        """
        if not isinstance(data, dict):
            return False
        if "employees" not in data or not isinstance(data["employees"], list):
            return False
        employees = data["employees"]
        if len(employees) == 0:
            return True
        first = employees[0]
        if not isinstance(first, dict):
            return False
        # 格式 A（Agent① 原始）：有 structured 字段
        if "structured" in first:
            required_agent1 = {
                "employee_id",
                "structured",
                "text_summaries",
                "scores_360",
                "performance",
                "training",
            }
            return all(k in first for k in required_agent1)
        # 格式 B（适配后）：有 raw 字段
        if "raw" in first:
            required_adapted = {
                "employee_id",
                "raw",
                "summary",
                "scores_360",
                "performance_history",
                "training",
            }
            return all(k in first for k in required_adapted)
        return False

    # ── LLM 提取（Day 2 Task 2.1）──

    def _llm_extract(self, employee: dict, context: dict) -> dict:
        """单员工 LLM 抽取 T1/T2/T3 raw 标签 + 大五。

        流程（第二周指南 Day 2 Task 2.1）：
          1. cancel 检查（基类 _check_cancel）
          2. offline 短路 → 返回空 t1/t2/big_five/t3_raw + model="offline-placeholder"
          3. 构造 system_prompt（嵌入标签库）+ user_prompt（员工数据）
          4. call_llm_json（temperature=0，不传 json_schema/timeout）
          5. 降级（D6/F7）：解析失败 → 确定性占位，禁第 2 次 LLM（防雪崩）
          6. 范围守卫（C4）：ability_score 夹紧 [0,100]、sfia_level [0,7]、confidence [0,1]

        Args:
            employee: 适配后员工 dict（含 raw/summary/scores_360/performance_history/training）。
            context: PipelineRunner 注入的上下文（含 cancel_event）。

        Returns:
            C1 对称契约：所有路径返回相同顶层 key 集合
            {content: dict|None, error: str|None, model: str, usage: dict,
             offline_skipped: bool}
            content 结构：{t1_professional, t2_behavioral, big_five, t3_raw}
        """
        # ── 1. cancel 检查 ──
        if self._check_cancel(context):
            return {
                "content": None,
                "error": "cancelled",
                "model": "",
                "usage": {},
                "offline_skipped": False,
            }

        emp_id = employee.get("employee_id", "") if isinstance(employee, dict) else ""

        # ── 2. offline 短路（参考 llm_summarizer:86）──
        if config.is_offline_mode():
            logger.info("Agent② _llm_extract offline 短路: %s", emp_id)
            return {
                "content": self._empty_extract(),
                "error": None,
                "model": "offline-placeholder",
                "usage": {},
                "offline_skipped": True,
            }

        # ── 3. 构造 prompts ──
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(employee)

        # ── 4. 调用 LLM ──
        # PROFILE_EXTRACT_LLM_TIMEOUT：per-employee 结构化 JSON 抽取输出比 Agent① summary 重，
        # LLM_API_TIMEOUT=30 实测偏紧（Paratera 代理按 token 计延迟，长 JSON 生成超 30s）
        result = call_llm_json(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.0,
            max_tokens=config.PROFILE_EXTRACT_MAX_TOKENS,
            timeout=config.PROFILE_EXTRACT_LLM_TIMEOUT,
        )

        # ── 5. 降级（D6/F7 防雪崩：解析失败不调第 2 次 LLM）──
        if result.get("error"):
            err = result["error"]
            parse_failure = (
                "empty content" in err
                or "JSON parse" in err
                or "Expecting value" in err
            )
            if parse_failure:
                logger.warning(
                    "Agent② _llm_extract 解析失败 (%s)，确定性降级（不调第 2 次 LLM）: %s",
                    err, emp_id,
                )
                return {
                    "content": self._empty_extract(),
                    "error": None,
                    "model": "degraded-placeholder",
                    "usage": result.get("usage", {}) or {},
                    "offline_skipped": False,
                }
            # 认证/限流/网络错误 → 返回 error 给调用方退避
            return {
                "content": None,
                "error": err,
                "model": result.get("model", ""),
                "usage": result.get("usage", {}) or {},
                "offline_skipped": False,
            }

        # ── 6. content 守卫 + 范围清洗 ──
        content = result.get("content")
        if not isinstance(content, dict):
            # C3/G：非 dict 守卫，错误信息含实际类型名
            return {
                "content": None,
                "error": f"LLM 返回非 dict 结构: {type(content).__name__}",
                "model": result.get("model", ""),
                "usage": result.get("usage", {}) or {},
                "offline_skipped": False,
            }

        content = self._clamp_extract_ranges(content)

        return {
            "content": content,
            "error": None,
            "model": result.get("model", ""),
            "usage": result.get("usage", {}) or {},
            "offline_skipped": False,
        }

    @staticmethod
    def _empty_extract() -> dict:
        """空提取结果（offline / degraded 占位）。供 Day 3 compute_t3_scores 全空 → confidence=0.3。

        C1 对称：所有返回路径 content key 集合固定
        = {t1_professional, t2_behavioral, big_five, t3_raw, t3_labels}
        （t3_labels 是 Step 1.4 新增：T3 升级为标签抽取通道的占位）。
        """
        return {
            "t1_professional": [],
            "t2_behavioral": [],
            "big_five": {
                d: 0 for d in config.BIG_FIVE_DIMENSIONS
            },
            "t3_raw": {
                "learning_activities": [],
                "career_roles": [],
                "growth_evidence": [],
                "feedback_signals": [],
            },
            "t3_labels": [],
        }

    def _build_system_prompt(self) -> str:
        """构造 system prompt，三通道分块引导（T1/T2/T3 独立抽取互不干涉）。

        双层三通道方案 §2.4：单次 LLM 调用，prompt 内三通道分块引导（成本不增）。
        - T1 通道：只看专业能力证据（项目/绩效/证书里的技术技能）
        - T2 通道：只看行为表现（360评价里的协作/沟通/执行行为）
        - T3 通道：只看潜质信号，**输出标签**（concept→标准标签，同 T1/T2 结构）
          证据模式引导（领导力潜质/成长型思维/自驱力/抗压韧性/战略眼光等）

        五层方案 §0：T0 已融合进 T1 层，corpus 不含独立 T0 tier；工具/领域/知识
        作为 T1 子类别（category=tool/domain/knowledge）。命中率提升（Step 8b）：
        每标签列 name + definition + keywords，让 LLM 能区分相似标签。
        few-shot 加 concept→standard_label 示例（arxiv 2310.11244：+3-17% F1）。
        """
        try:
            corpus = load_label_corpus()
        except Exception as e:
            logger.warning("load_label_corpus 失败，system prompt 用空标签库: %s", e)
            corpus = []

        # 按 category 分组，每标签含 name + definition + keywords（紧凑格式）
        by_cat: dict[str, list[dict]] = {}
        for item in corpus:
            cat = item.get("category", "skill")
            by_cat.setdefault(cat, []).append(item)

        def _fmt_items(items: list[dict]) -> list[str]:
            out = []
            for it in items:
                name = it.get("name", "")
                definition = it.get("definition", "") or ""
                keywords = it.get("keywords", []) or []
                kw_str = f" [关键词: {', '.join(keywords)}]" if keywords else ""
                out.append(f"    - {name}: {definition}{kw_str}")
            return out

        # ── 三通道分块 ──
        lines: list[str] = []

        # T1 通道（skill/tool/domain/knowledge）
        t1_lines: list[str] = []
        cat_label_t1 = {
            "skill": "技能（T1 skill）",
            "tool": "工具（T1 tool）",
            "domain": "领域（T1 domain）",
            "knowledge": "知识体系（T1 knowledge）",
        }
        for cat in ["skill", "tool", "domain", "knowledge"]:
            items = by_cat.get(cat, [])
            if not items:
                continue
            t1_lines.append(f"  {cat_label_t1[cat]}:")
            t1_lines.extend(_fmt_items(items))
        lines.append("【T1 通道·专业能力】只看专业能力证据（项目/绩效/证书里的技术技能）：")
        lines.extend(t1_lines if t1_lines else ["  (T1 标签库加载失败)"])

        # T2 通道（behavior）
        t2_items = by_cat.get("behavior", [])
        lines.append("\n【T2 通道·行为能力】只看行为表现（360评价里的协作/沟通/执行行为）：")
        if t2_items:
            lines.append("  行为能力（T2 behavior）:")
            lines.extend(_fmt_items(t2_items))
        else:
            lines.append("  (T2 标签库加载失败)")

        # T3 通道（potential）——升级为标签抽取
        t3_items = by_cat.get("potential", [])
        lines.append("\n【T3 通道·发展潜力】只看潜质信号，输出标准标签（concept→standard_label）。")
        lines.append("  证据模式引导（据信号判潜质标签，不要求每项都抽，有证据才抽）：")
        lines.append("  - 领导力潜质：非职权影响力（承担 leader 角色/为下属争取资源/关键时刻兜底）")
        lines.append("  - 成长型思维：逆境反弹（绩效轨迹如 B→C→A 翻盘 + 主动学习）")
        lines.append("  - 自驱力：内生动力（主动承担/主动学，P1 即显潜质）")
        lines.append("  - 抗压韧性：逆境产出稳定（绩效如 D→C→B + 关键时刻兜底）")
        lines.append("  - 战略眼光：跨域视野/战略意识")
        if t3_items:
            lines.append("  发展潜力标签库（T3 standard_label 从中选取）:")
            lines.extend(_fmt_items(t3_items))
        else:
            lines.append("  (T3 标签库加载失败)")

        label_block = "\n".join(lines)

        # few-shot 示例：T1/T2 通道（concept 必须是抽象能力名，展示「原文→抽象 concept→标准标签」三步）
        # 🔴 Step 1.10 修复：旧 few-shot 的 concept 是原文短语（"参与工业IoT管理平台"），
        # LLM 照搬导致 cross-encoder 对（长原文, 标签）打分天然低 → recall@GT 虚低。
        # 新 few-shot 明确 concept 是抽象名（≤8 字能力词），并展示从原文提炼的步骤。
        few_shot_t1t2 = (
            "\n示例（concept 必须是抽象能力名，从原文提炼后映射；禁止照抄原文片段）：\n"
            '  原文「参与工业IoT管理平台，负责核心模块开发，涉及gRPC」'
            ' → concept="物联网开发" → standard_label="智能制造" '
            '(IoT 平台服务于智能制造生产流程)\n'
            '  原文「创新引入Java微服务方案，效率提升30%」'
            ' → concept="Java后端开发" → standard_label="Java开发" '
            '(微服务是架构风格，开发技能归属 Java开发)\n'
            '  原文「自然承担 leader 角色，具备基层管理能力」'
            ' → concept="团队领导" → standard_label="团队管理" '
            '(leader 角色体现团队管理行为)\n'
            '  ❌ 错误：concept="工业大数据分析平台中Airflow等技术应用"（照抄原文，太长太具体）\n'
            '  ✅ 正确：concept="数据分析"（抽象能力名）\n'
        )
        # T3 few-shot（concept 同样抽象化；用 GT 员工真实信号；实验结论需标注"含 few-shot 提示"）
        few_shot_t3 = (
            "示例（T3 通道 concept 抽象化后映射 standard_label）：\n"
            '  原文「为下属争取资源、关键时刻能兜底」'
            ' → concept="非职权影响力" → standard_label="领导力潜质" '
            '(非职权影响力属领导力潜质，非团队管理行为)\n'
            '  原文「绩效 B→C→A 翻盘 + 主动学习新技术」'
            ' → concept="逆境反弹" → standard_label="成长型思维" '
            '(逆境反弹+主动学习属成长型思维)\n'
        )

        return (
            "你是 HR 胜任力分析助手。任务：从员工人事文本中按三通道独立提取能力标签，"
            "映射到下方标准标签库，并评定能力等级与能力分。\n"
            "三通道独立抽取互不干涉：T1 只看专业能力证据、T2 只看行为表现、T3 只看潜质信号。"
            "严格基于原文，不添加原文中没有的信息，不做推断。"
            "证据 text_snippet 必须是原文精确子串（≤20 字）。\n\n"
            "🔴 concept 字段规则（重要）：concept 必须是【抽象能力名】，"
            "是员工具备的能力/行为的概括词（如「数据分析」「嵌入式开发」「团队领导」「逆境反弹」），"
            "长度 ≤8 字，是一个名词短语。禁止把原文片段、项目名、长句直接作为 concept。"
            "先从原文提炼出抽象能力，再写入 concept，最后映射到 standard_label。\n\n"
            f"标准标签库（standard_label 必须从中选取，参考 definition/keywords 区分相似标签）：\n"
            f"{label_block}\n\n"
            f"{few_shot_t1t2}\n"
            f"{few_shot_t3}\n"
            "category 取值：T1 用 skill/tool/domain/knowledge 之一（按标签库归属），"
            "T2 固定 behavior，T3 固定 potential。"
            "T3 标签不挂 sfia_level/ability_score（潜质用 confidence 表达），其他通道"
            "sfia_level 整数 0-7（IT 类）/通用能力等级整数 1-5（非 IT 类）；"
            "ability_score 整数 0-100；confidence 浮点 0-1。"
        )

    def _build_user_prompt(self, employee: dict) -> str:
        """构造 user prompt，嵌入员工数据。"""
        emp = employee if isinstance(employee, dict) else {}
        raw = emp.get("raw") or {}
        if not isinstance(raw, dict):
            raw = {}
        summary = emp.get("summary") or {}
        if not isinstance(summary, dict):
            summary = {}
        scores_360 = emp.get("scores_360") or {}
        if not isinstance(scores_360, dict):
            scores_360 = {}
        perf_hist = emp.get("performance_history") or []
        if not isinstance(perf_hist, list):
            perf_hist = []
        training = emp.get("training") or []
        if not isinstance(training, list):
            training = []

        # 绩效序列（如 "2024:A / 2025:B"）
        perf_seq = " / ".join(
            f"{p.get('year','')}:{p.get('grade','')}" for p in perf_hist
            if isinstance(p, dict)
        ) or "无"

        # 360 维度分数
        dims = scores_360.get("dimensions") or {}
        if not isinstance(dims, dict):
            dims = {}
        dims_str = ", ".join(f"{k}={v}" for k, v in dims.items()) or "无"

        # 培训课程名
        courses = ", ".join(
            t.get("course_name", "") for t in training
            if isinstance(t, dict) and t.get("course_name")
        ) or "无"

        certs = raw.get("certificates") or "无"
        job_seq = raw.get("job_sequence") or "未指定"

        summary_perf = summary.get("performance_summary") or ""
        summary_proj = summary.get("project_summary") or ""
        summary_eval = summary.get("evaluation_summary") or ""

        return f"""员工ID: {emp.get('employee_id','')}
岗位序列: {job_seq}
职级: {raw.get('current_level','')}
工龄: {raw.get('years_of_service','')}
证书: {certs}

绩效历史: {perf_seq}

绩效摘要:
{summary_perf}

项目摘要:
{summary_proj}

360评价摘要:
{summary_eval}

360维度分数: {dims_str}
培训课程: {courses}

请基于以上信息，严格输出以下 JSON（不要 markdown 代码块，不要额外解释）：
{{
    "t1_professional": [
        {{"concept": "原文能力概念", "standard_label": "标签库中的标准标签名", "category": "skill|tool|domain|knowledge", "sfia_level": 0, "ability_score": 0, "confidence": 0.0, "evidence": [{{"source": "绩效评语_2024", "text_snippet": "原文片段"}}]}}
    ],
    "t2_behavioral": [
        {{"concept": "原文行为概念", "standard_label": "标签库中的标准标签名", "category": "behavior", "sfia_level": 0, "ability_score": 0, "confidence": 0.0, "evidence": [{{"source": "360评价_2024", "text_snippet": "原文片段"}}]}}
    ],
    "t3_labels": [
        {{"concept": "原文潜质信号", "standard_label": "T3 标签库中的标准标签名", "category": "potential", "confidence": 0.0, "evidence": [{{"source": "360评价_2024", "text_snippet": "原文片段"}}]}}
    ],
    "big_five": {{"openness": 0, "conscientiousness": 0, "extraversion": 0, "agreeableness": 0, "neuroticism": 0}},
    "t3_raw": {{"learning_activities": [], "career_roles": [], "growth_evidence": [], "feedback_signals": []}}
}}"""

    def _clamp_extract_ranges(self, content: dict) -> dict:
        """范围守卫（C4）：LLM 可能输出越界值，夹紧到合法范围。

        三通道覆盖（Step 1.6）：
        - T1/T2 项：ability_score → [0,100]、sfia_level → [0,7]、confidence → [0,1]
        - T3 项（t3_labels）：只夹紧 confidence（T3 不挂等级，无 sfia_level/ability_score）
        - big_five 各维 → [0, 100]

        ability_score 缺失兜底（Step 1.2 接线）：T1/T2 项若 LLM 未给 ability_score 但给了
        sfia_level（IT/T2）或 general_level（非 IT），用 ability_score_from_level 映射补全；
        LLM 已给 ability_score 仅夹紧不重算（保 LLM 基于证据的判断，不覆盖）。

        D2 去重：删除内嵌 _clamp_int，复用 utils.label_embedding.clamp_int（单一来源）。
        守卫失败的字段保留并夹紧，不丢弃数据（C8）。
        """
        def _clamp_float(v, lo, hi):
            try:
                x = float(v)
            except (TypeError, ValueError):
                return lo
            return max(lo, min(hi, x))

        # T1/T2 项：等级 + 能力分 + 置信度
        for key in ("t1_professional", "t2_behavioral"):
            items = content.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                if "sfia_level" in item:
                    item["sfia_level"] = clamp_int(
                        item["sfia_level"], 0, config.SFIA_MAX_LEVEL
                    )
                # ability_score：LLM 给了仅夹紧；缺失但有 level → 映射补全
                if "ability_score" in item:
                    item["ability_score"] = clamp_int(
                        item["ability_score"],
                        config.ABILITY_SCORE_MIN, config.ABILITY_SCORE_MAX,
                    )
                else:
                    # T2 强制 SFIA；T1 据标签名判框架（IT_T1_TAG_NAMES）
                    is_it = (key == "t2_behavioral") or None
                    mapped = ability_score_from_level(
                        item.get("standard_label", ""),
                        sfia_level=item.get("sfia_level"),
                        general_level=item.get("general_level"),
                        is_it_label=is_it,
                    )
                    if mapped != 0 or item.get("sfia_level") is not None or item.get("general_level") is not None:
                        item["ability_score"] = mapped
                if "confidence" in item:
                    item["confidence"] = _clamp_float(item["confidence"], 0.0, 1.0)

        # T3 项：只夹紧 confidence（T3 不挂等级）
        t3_items = content.get("t3_labels")
        if isinstance(t3_items, list):
            for item in t3_items:
                if isinstance(item, dict) and "confidence" in item:
                    item["confidence"] = _clamp_float(item["confidence"], 0.0, 1.0)

        big_five = content.get("big_five")
        if isinstance(big_five, dict):
            for dim in config.BIG_FIVE_DIMENSIONS:
                if dim in big_five:
                    big_five[dim] = clamp_int(big_five[dim], 0, 100)


        return content

    # ── 执行（Day 1 骨架）──

    def execute(self, data: dict, context: dict) -> dict:
        """Day 1 骨架：输入适配 → Phase 0 加载 corpus → Phase 1 占位 → 清洗返回。

        Day 3 将实现 Phase 1 并行池 + LLM 提取 + Embedding 验证 + T3 分数。
        """
        # 🔴 输入适配：检测 Agent① 原始格式并转换
        employees = data.get("employees") if isinstance(data, dict) else None
        if (
            employees
            and isinstance(employees, list)
            and len(employees) > 0
            and isinstance(employees[0], dict)
            and "structured" in employees[0]
        ):
            data = self._adapt_input(data)
            employees = data.get("employees", [])

        # 空员工列表 → degraded（不阻断 pipeline）
        if not employees:
            return {
                "status": "degraded",
                "data": {"employees": [], "stats": {}},
                "metadata": {"error": "empty employee list"},
            }

        # ── Phase 0: 加载标签库 corpus + 预编码文本矩阵（只做一次）──
        # 模型懒加载：get_embedding_model() 首次 encode 时触发
        # corpus_text_vecs 预编码一次，所有员工/所有 concept 复用（避免逐 concept 重算矩阵）
        # offline 模式跳过编码（不加载 bge 模型，offline 路径不用 embedding）
        try:
            _corpus = load_label_corpus(config.LABEL_LIBRARY_PATH)
            if _corpus and not config.is_offline_mode():
                corpus_texts = [c.get("text", "") for c in _corpus]
                _corpus_vecs = encode_labels(tuple(corpus_texts))
            else:
                _corpus_vecs = None
        except Exception as e:
            logger.warning("Agent② Phase 0 corpus 加载/编码失败: %s — Stage 2+3 降级", e)
            _corpus = []
            _corpus_vecs = None

        # ── Phase 1: 三阶段串联（demo 期 max_workers=3 并发）──
        # 每员工：_llm_extract(Stage1) → recall_top_k(Stage2) → rerank_label_llm(Stage3)
        #         → compute_t3_scores → 注入 matched_label/mapping_source 等字段
        # F3 线程风险点：cancel_event 进 worker 即查、超时用 future.result(timeout)+cancel
        #   不重试（Python 线程不可真杀），超时员工走 degraded 不阻断 pipeline
        max_workers = min(3, len(employees)) or 1
        profiles: list[dict] = []
        per_emp_stats: list[dict] = []

        def _run_one(emp: dict) -> tuple[dict, dict]:
            return self._process_employee(
                emp, context, _corpus, _corpus_vecs
            )

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(_run_one, emp) for emp in employees]
            for i, emp in enumerate(employees):
                fut = futures[i]
                try:
                    profile, emp_stats = fut.result(
                        timeout=config.AGENT_PROFILE_TIMEOUT
                    )
                    profiles.append(profile)
                    per_emp_stats.append(emp_stats)
                except FuturesTimeoutError:
                    # F3：不重试，cancel 通知 worker 退出，员工降级
                    fut.cancel()
                    logger.warning("Agent② 员工超时降级: %s", emp.get("employee_id", ""))
                    profiles.append(self._degraded_profile(emp, "per_emp_timeout", ""))
                    per_emp_stats.append({
                        "llm_calls": 0, "rerank_calls": 0,
                        "rerank_failures": 0, "new_labels": 0,
                        "exact_matches": 0, "offline_skipped": False,
                        "timeout": True,
                    })
                except Exception as e:
                    logger.warning("Agent② 员工处理异常降级 %s: %s",
                                   emp.get("employee_id", ""), e)
                    profiles.append(self._degraded_profile(emp, f"exception: {e}", ""))
                    per_emp_stats.append({
                        "llm_calls": 0, "rerank_calls": 0,
                        "rerank_failures": 0, "new_labels": 0,
                        "exact_matches": 0, "offline_skipped": False,
                        "exception": True,
                    })

        # ── 聚合 stats（主线程汇总，worker 不写共享状态）──
        def _sum(key):
            return sum(s.get(key, 0) for s in per_emp_stats)
        stats = {
            "total": len(employees),
            "llm_calls": _sum("llm_calls"),
            "rerank_calls": _sum("rerank_calls"),
            "rerank_failures": _sum("rerank_failures"),
            "new_labels": _sum("new_labels"),
            "exact_matches": _sum("exact_matches"),
            "offline_skipped_llm": _sum("offline_skipped"),
            "timeouts": _sum("timeout"),
            "exceptions": _sum("exception"),
        }
        result = {"employees": profiles, "stats": stats}

        # ── 返回前 numpy 类型清洗（递归处理所有嵌套层级）──
        # ⚠ PipelineRunner._save_intermediate 的 numpy 清洗仅对 data 为 list[dict] 触发，
        #   Agent② 输出 data 为 dict 格式，不在自动清洗范围 → 显式调用不可省略。
        result = numpy_to_native(result)

        return {"status": "success", "data": result, "metadata": {}}

    # ── Phase 1 辅助方法 ──

    def _process_employee(
        self, employee: dict, context: dict,
        corpus: list[dict], corpus_vecs,
    ) -> tuple[dict, dict]:
        """单员工三阶段串联：Stage1 抽取 → Stage2 召回 → Stage3 重排 → T3。

        Returns:
            (profile, stats) — profile 含 t1/t2 每项注入匹配字段 + t3_potential；
            stats 为该员工的局部计数（主线程聚合，避免 worker 写共享状态 F3）。
        """
        emp_id = employee.get("employee_id", "")
        emp_stats = {
            "llm_calls": 0, "rerank_calls": 0, "rerank_failures": 0,
            "new_labels": 0, "exact_matches": 0, "offline_skipped": False,
        }

        # F3：进 worker 先查 cancel
        if self._check_cancel(context):
            return self._degraded_profile(employee, "cancelled", ""), emp_stats

        # ── Stage 1: LLM 抽取 ──
        extract = self._llm_extract(employee, context)
        if not extract.get("offline_skipped"):
            emp_stats["llm_calls"] = 1
        if extract.get("error") or extract.get("offline_skipped"):
            # offline 已短路（content 是空 extract）；error 退避 → 降级
            if extract.get("offline_skipped"):
                emp_stats["offline_skipped"] = True
                # offline：content 是 _empty_extract，仍跑 compute_t3_scores（全空→0.3）
                content = extract.get("content") or self._empty_extract()
                profile = self._assemble_profile(
                    employee, content, extract.get("model", "offline-placeholder"),
                    offline=True, corpus=None, corpus_vecs=None, emp_stats=emp_stats,
                )
                return profile, emp_stats
            return self._degraded_profile(
                employee, f"llm_error: {extract['error']}", extract.get("model", "")
            ), emp_stats

        content = extract.get("content") or {}

        # ── Stage 2+3: 召回 + 重排（corpus 加载失败时降级 trust LLM）──
        if corpus:
            rerank_items, idx_map = self._collect_rerank_items(content, corpus, corpus_vecs, emp_stats)
            if rerank_items:
                emp_stats["rerank_calls"] = 1
                # Step 8d：cross-encoder 精排优先，加载失败内部降级到 rerank_label_llm
                rerank_results = rerank_cross_encoder(
                    rerank_items, employee, corpus,
                )
                self._inject_mapping_fields(content, rerank_results, idx_map, emp_stats)
            else:
                # 无可重排项（空 t1/t2 或全无 concept）→ 跳过
                pass
        else:
            # corpus 加载失败 → 所有项标记 corpus_load_failed_trust_llm
            self._mark_corpus_failed(content, emp_stats)

        # ── compute_t3_scores ──
        content["t3_potential"] = compute_t3_scores(
            content.get("t3_raw"), employee
        )

        profile = {
            "employee_id": emp_id,
            "model": extract.get("model", ""),
            "usage": extract.get("usage", {}) or {},
            "status": "success",
            "t1_professional": content.get("t1_professional", []),
            "t2_behavioral": content.get("t2_behavioral", []),
            "big_five": content.get("big_five", {}),
            "t3_raw": content.get("t3_raw", {}),
            "t3_labels": content.get("t3_labels", []),
            "t3_potential": content["t3_potential"],
        }
        return profile, emp_stats

    def _collect_rerank_items(
        self, content: dict, corpus: list[dict], corpus_vecs, emp_stats: dict,
    ) -> tuple[list[dict], list[tuple[str, int]]]:
        """收集 t1+t2+t3_labels 每项，调 recall_top_k 取候选，构造 rerank 输入。

        Step 1.5：T3 通道升级为标签抽取后，t3_labels 项同 t1/t2 走 recall→rerank。
        T3 项的 concept 调 recall_top_k 在 T3 corpus（9 标签）召回候选。

        Returns:
            (rerank_items, idx_map) — idx_map[i] = (key, pos) 把 rerank 第 i 项映射回
            content[key][pos] 用于注入。
        """
        rerank_items: list[dict] = []
        idx_map: list[tuple[str, int]] = []
        i = 0
        for key in ("t1_professional", "t2_behavioral", "t3_labels"):
            items = content.get(key, []) or []
            if not isinstance(items, list):
                continue
            for pos, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                concept = item.get("concept", "")
                if not concept:
                    continue
                candidates_pairs = recall_top_k(
                    concept, corpus, corpus_text_vecs=corpus_vecs,
                )
                candidates = [name for name, _ in candidates_pairs]
                rerank_items.append({
                    "idx": i,
                    "concept": concept,
                    "standard_label": item.get("standard_label", ""),
                    "category": item.get("category", ""),
                    "candidates": candidates,
                    "extract_confidence": item.get("confidence", 0.5),
                })
                idx_map.append((key, pos))
                i += 1
        return rerank_items, idx_map

    @staticmethod
    def _inject_mapping_fields(
        content: dict, rerank_results: list[dict],
        idx_map: list[tuple[str, int]], emp_stats: dict,
    ) -> None:
        """把 rerank 结果注入回 content[key][pos]，并聚合 emp_stats。"""
        for i, res in enumerate(rerank_results):
            if i >= len(idx_map):
                break
            key, pos = idx_map[i]
            items = content.get(key, [])
            if not isinstance(items, list) or pos >= len(items):
                continue
            item = items[pos]
            if not isinstance(item, dict):
                continue
            source = res.get("mapping_source", "")
            item["matched_label"] = res.get("matched_label", "")
            item["is_new_label"] = res.get("is_new_label", False)
            item["mapping_source"] = source
            item["match_confidence"] = res.get("match_confidence", 0.0)
            item["rerank_candidates"] = res.get("candidates_seen", [])
            item["rerank_rationale"] = res.get("rationale", "")
            # 聚合 emp_stats（cross-encoder source 与 LLM source 对齐同类统计）
            if source in ("exact_name_match", "exact_name_match_dup"):
                emp_stats["exact_matches"] += 1
            elif source in ("new_label", "cross_encoder_new_label"):
                emp_stats["new_labels"] += 1
            elif source in ("rerank_failed_trust_llm", "rerank_failed_fallback_llm"):
                emp_stats["rerank_failures"] += 1

    @staticmethod
    def _mark_corpus_failed(content: dict, emp_stats: dict) -> None:
        """corpus 加载失败：所有 t1/t2/t3_labels 项标记 corpus_load_failed_trust_llm。"""
        count = 0
        for key in ("t1_professional", "t2_behavioral", "t3_labels"):
            items = content.get(key, []) or []
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    item["matched_label"] = item.get("standard_label", "")
                    item["is_new_label"] = False
                    item["mapping_source"] = "corpus_load_failed_trust_llm"
                    item["match_confidence"] = item.get("confidence", 0.5)
                    item["rerank_candidates"] = []
                    item["rerank_rationale"] = "corpus 加载失败，信任 LLM 原始提议"
                    count += 1
        emp_stats["rerank_failures"] = count

    def _assemble_profile(
        self, employee: dict, content: dict, model: str,
        offline: bool, corpus, corpus_vecs, emp_stats: dict,
    ) -> dict:
        """组装 offline 路径的 profile（content 是 _empty_extract，跑 compute_t3_scores）。"""
        # offline：所有 t1/t2 项（空）标记 offline_skipped；compute_t3_scores 全空→0.3
        content["t3_potential"] = compute_t3_scores(
            content.get("t3_raw"), employee
        )
        return {
            "employee_id": employee.get("employee_id", ""),
            "model": model,
            "usage": {},
            "status": "offline" if offline else "degraded",
            "t1_professional": content.get("t1_professional", []),
            "t2_behavioral": content.get("t2_behavioral", []),
            "big_five": content.get("big_five", {}),
            "t3_raw": content.get("t3_raw", {}),
            "t3_labels": content.get("t3_labels", []),
            "t3_potential": content["t3_potential"],
        }

    def _degraded_profile(self, employee: dict, reason: str, model: str) -> dict:
        """降级 profile（超时/异常/error）：空 t1/t2 + t3_potential 全空。"""
        empty = self._empty_extract()
        empty["t3_potential"] = compute_t3_scores(None, employee)
        return {
            "employee_id": employee.get("employee_id", ""),
            "model": model,
            "usage": {},
            "status": "degraded",
            "degraded_reason": reason,
            "t1_professional": empty["t1_professional"],
            "t2_behavioral": empty["t2_behavioral"],
            "big_five": empty["big_five"],
            "t3_raw": empty["t3_raw"],
            "t3_labels": empty["t3_labels"],
            "t3_potential": empty["t3_potential"],
        }

    # ── Schema（对齐 docs/plan-profile-agent-schema.md）──

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "employees": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "llm_stats": {"type": "object"},
            },
            "required": ["employees"],
        }

    def get_output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["success", "degraded", "error"]},
                "data": {
                    "type": "object",
                    "properties": {
                        "employees": {"type": "array"},
                        "stats": {"type": "object"},
                    },
                },
                "metadata": {"type": "object"},
            },
            "required": ["status", "data", "metadata"],
        }
