"""Agent① 数据理解Agent

读取多源员工数据 → 缺失值检测 → LLM 文本摘要 → 360 评价预处理 → 输出融合数据表。

---
文件：agents/data_understanding.py
项目：Talent Compass
依循：《多Agent协作完整行为逻辑与实现方法.md》Agent① 步骤 1.1~1.5
     《第一周开发指南_vibe-coding.md》Task 3.1
"""

import json
import os
import time
import logging
from datetime import datetime, timezone

import pandas as pd
import numpy as np

from agents.base_agent import BaseAgent
from config import (
    RAW_DATA_DIR,
    EVALUATOR_MIN_SAMPLE_SIZE,
    AGENT_DATAUNDERSTANDING_TIMEOUT,
)
from utils.llm_client import call_llm_json

logger = logging.getLogger(__name__)

# ── 必填列定义（D2: 单一来源） ──────────────────────────────────────
REQUIRED_COLUMNS = {
    "employees": {"employee_id", "name", "age", "gender", "education", "major",
                  "job_sequence", "current_position", "current_level",
                  "hire_date", "years_of_service"},
    "performance": {"employee_id", "year", "performance_grade", "performance_comment"},
    "projects": {"employee_id", "project_name", "role", "description", "tools_used"},
    "training": {"employee_id", "course_name", "completion_date", "status", "score"},
    "evaluation_360": {"employee_id", "evaluator_id", "evaluator_role", "dimension",
                       "score", "comment"},
}

# ── 360 评价角色权重（基线） ────────────────────────────────────────
# 来源：《多Agent协作完整行为逻辑与实现方法.md》Agent① 360评价者权重分配
# 排除自评后归一化，和 = 1.0
ROLE_WEIGHTS_BASELINE = {
    "上级": 0.47,
    "同事": 0.26,
    "下属": 0.13,
    "HR": 0.14,
}
SELF_ROLE = "自评"

# 角色权重调节（按岗位类型）
ROLE_ADJUSTMENTS = {
    "技术研发类": {"上级": -0.09, "同事": 0.09},   # 同事权重上调至 0.35，上级下调至 0.38
    "管理职能类": {"下属": 0.05, "上级": -0.05},  # 下属上调至 0.18，上级下调至 0.42
}

# 360 评价维度
KNOWN_DIMENSIONS = {"专业能力", "沟通协作", "领导力", "责任心", "学习能力"}

# LLM 频率控制常量
LLM_CALL_SLEEP = 0.5
LLM_BACKOFF_BASE = 2
LLM_BACKOFF_MAX = 15
LLM_CANCEL_CHECK_INTERVAL = 10


class DataUnderstanding(BaseAgent):
    """Agent① 数据理解Agent。

    读取 5 个数据源文件 → 缺失值检测 → LLM 文本摘要 → 360 预处理 → 融合输出。
    """

    agent_name = "DataUnderstanding"
    agent_version = "0.1.0"
    # 覆盖 PipelineRunner 默认 120s：100 人 × ~3.5s/人 ≈ 350s
    timeout_seconds = AGENT_DATAUNDERSTANDING_TIMEOUT

    # ── 公共方法 ──────────────────────────────────────────────────

    def validate_input(self, data: dict) -> bool:
        """校验输入数据是否符合本 Agent 的输入 Schema。"""
        if not isinstance(data, dict):
            return False

        required_keys = ["employees", "performance", "projects", "training", "evaluation_360"]
        for key in required_keys:
            path = data.get(key)
            if not isinstance(path, str) or not path.strip():
                logger.error(f"DataUnderstanding: {key} 路径无效: {path!r}")
                return False
            if not os.path.isfile(path):
                logger.error(f"DataUnderstanding: 文件不存在: {path}")
                return False

        # 快速校验列名
        try:
            emp_cols = set(pd.read_csv(data["employees"], nrows=0).columns)
            if not REQUIRED_COLUMNS["employees"].issubset(emp_cols):
                missing = REQUIRED_COLUMNS["employees"] - emp_cols
                logger.error(f"employees.csv 缺少必填列: {missing}")
                return False

            perf_cols = set(pd.read_csv(data["performance"], nrows=0).columns)
            if not REQUIRED_COLUMNS["performance"].issubset(perf_cols):
                missing = REQUIRED_COLUMNS["performance"] - perf_cols
                logger.error(f"performance.csv 缺少必填列: {missing}")
                return False

            # JSON 文件不能使用 nrows=0；读第一条记录校验列名
            with open(data["projects"], "r", encoding="utf-8-sig") as _jf:
                _first_proj = json.load(_jf)
            proj_cols = set(_first_proj[0].keys()) if _first_proj else set()
            if not REQUIRED_COLUMNS["projects"].issubset(proj_cols):
                missing = REQUIRED_COLUMNS["projects"] - proj_cols
                logger.error(f"projects.json 缺少必填列: {missing}")
                return False

            train_cols = set(pd.read_csv(data["training"], nrows=0).columns)
            if not REQUIRED_COLUMNS["training"].issubset(train_cols):
                missing = REQUIRED_COLUMNS["training"] - train_cols
                logger.error(f"training.csv 缺少必填列: {missing}")
                return False

            eval_cols = set(pd.read_csv(data["evaluation_360"], nrows=0).columns)
            if not REQUIRED_COLUMNS["evaluation_360"].issubset(eval_cols):
                missing = REQUIRED_COLUMNS["evaluation_360"] - eval_cols
                logger.error(f"evaluation_360.csv 缺少必填列: {missing}")
                return False
        except Exception as e:
            logger.error(f"DataUnderstanding 输入校验异常: {e}")
            return False

        return True

    def execute(self, data: dict, context: dict) -> dict:
        """核心入口：串联步骤 1.1 ~ 1.5。"""
        trace_id = context.get("trace_id", "-")
        logger.info(f"DataUnderstanding 开始执行", extra={"trace_id": trace_id})

        # ── Step 1.1: 读取多源数据 ────────────────────────────────────
        dfs = self._read_data_files(data)
        if dfs is None:
            return {
                "status": "error",
                "data": None,
                "metadata": {"error": "数据文件读取失败"},
            }

        employees_df = dfs["employees"]
        perf_df = dfs["performance"]
        proj_df = dfs["projects"]
        train_df = dfs["training"]
        eval_df = dfs["evaluation_360"]

        # ── Step 1.2: 缺失值检测 ──────────────────────────────────────
        data_quality = self._detect_missing(dfs)
        logger.info(
            f"数据质量报告: {data_quality['total_employees']} 员工, "
            f"{data_quality['text_insufficient_count']} 文本不足",
            extra={"trace_id": trace_id},
        )

        # ── Step 1.3: 非结构化文本语义理解（LLM 调用） ────────────────
        summaries, llm_stats = self._process_employees(
            employees_df, perf_df, proj_df, eval_df, context
        )
        logger.info(
            f"LLM 摘要完成: {llm_stats['succeeded']}/{llm_stats['total']} 成功",
            extra={"trace_id": trace_id},
        )

        # ── Step 1.4: 360 评价预处理 ───────────────────────────────────
        scores_360 = self._preprocess_360(eval_df, employees_df)
        logger.info(
            f"360 预处理完成",
            extra={"trace_id": trace_id},
        )

        # ── Step 1.5: 融合输出 ────────────────────────────────────────
        employee_records = self._merge_records(
            employees_df, perf_df, proj_df, train_df,
            summaries, scores_360, data_quality,
        )

        # 移除 scores_360 中的辅助键
        scores_360.pop("_summary", None)
        scores_360.pop("_evaluators_skipped", None)

        output = {
            "employees": employee_records,
            "data_quality_report": data_quality,
            "llm_stats": llm_stats,
            "scores_360": scores_360,
        }

        skipped = data_quality.get("text_insufficient_count", 0)
        metadata = {
            "total_employees": data_quality["total_employees"],
            "llm_calls": llm_stats["total"],
            "llm_succeeded": llm_stats["succeeded"],
            "llm_total_tokens": llm_stats["total_tokens"],
            "skipped_text_insufficient": skipped,
            "error": None,
        }

        return {
            "status": "success" if llm_stats["succeeded"] > 0 else "degraded",
            "data": output,
            "metadata": metadata,
        }

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "required": ["employees", "performance", "projects", "training", "evaluation_360"],
            "properties": {
                "employees": {"type": "string", "description": "employees.csv 路径"},
                "performance": {"type": "string", "description": "performance.csv 路径"},
                "projects": {"type": "string", "description": "projects.json 路径"},
                "training": {"type": "string", "description": "training.csv 路径"},
                "evaluation_360": {"type": "string", "description": "evaluation_360.csv 路径"},
            },
        }

    def get_output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "employees": {"type": "array"},
                "data_quality_report": {"type": "object"},
                "llm_stats": {"type": "object"},
                "scores_360": {"type": "object"},
            },
        }

    # ── 步骤 1.1: 读取多源数据 ──────────────────────────────────────

    def _read_data_files(self, data: dict) -> dict | None:
        """读取 5 个数据源文件，返回 {df_name: DataFrame}。"""
        try:
            employees = pd.read_csv(data["employees"], dtype={"employee_id": str})
            performance = pd.read_csv(data["performance"], dtype={"employee_id": str})
            # JSON 文件可能有 BOM (utf-8-sig)，pd.read_json 不支持 BOM
            with open(data["projects"], "r", encoding="utf-8-sig") as _jf:
                _proj_data = json.load(_jf)
            projects = pd.DataFrame(_proj_data) if isinstance(_proj_data, list) else pd.DataFrame()
            training = pd.read_csv(data["training"], dtype={"employee_id": str})
            evaluation_360 = pd.read_csv(data["evaluation_360"], dtype={"employee_id": str})
        except Exception as e:
            logger.error(f"数据文件读取失败: {e}")
            return None

        # 确保 tools_used 是列表
        if "tools_used" in projects.columns:
            projects["tools_used"] = projects["tools_used"].apply(
                lambda x: x if isinstance(x, list) else []
            )

        return {
            "employees": employees,
            "performance": performance,
            "projects": projects,
            "training": training,
            "evaluation_360": evaluation_360,
        }

    # ── 步骤 1.2: 缺失值检测 ──────────────────────────────────────

    def _detect_missing(self, dfs: dict) -> dict:
        """检测各数据源的缺失值，返回数据质量报告。"""
        employees = dfs["employees"]
        total = len(employees)

        missing_summary = {}
        for name, df in dfs.items():
            missing_counts = df.isnull().sum()
            missing_summary[name] = {
                col: int(cnt) for col, cnt in missing_counts.items() if cnt > 0
            }

        severe_employees = []
        text_insufficient_count = 0

        for _, emp in employees.iterrows():
            emp_id = emp.get("employee_id", "?")
            emp_missing = 0
            emp_total = 0

            emp_fields = ["name", "age", "gender", "education", "major",
                          "job_sequence", "current_position", "current_level"]
            for f in emp_fields:
                emp_total += 1
                if pd.isna(emp.get(f)):
                    emp_missing += 1

            perf = dfs["performance"]
            emp_perf = perf[perf["employee_id"] == emp_id]
            has_perf_text = (
                emp_perf["performance_comment"].dropna()
                .astype(str).str.strip().ne("").any()
            )

            proj = dfs["projects"]
            emp_proj = proj[proj["employee_id"] == emp_id]
            has_proj_desc = (
                emp_proj["description"].dropna()
                .astype(str).str.strip().ne("").any()
            )

            eval360 = dfs["evaluation_360"]
            emp_eval = eval360[eval360["employee_id"] == emp_id]
            has_eval_comment = (
                emp_eval["comment"].dropna()
                .astype(str).str.strip().ne("").any()
            )

            if not (has_perf_text or has_proj_desc or has_eval_comment):
                text_insufficient_count += 1

            if emp_missing > 0 and (emp_missing / max(emp_total, 1)) > 0.5:
                severe_employees.append(emp_id)

        return {
            "total_employees": total,
            "missing_summary": missing_summary,
            "severe_missing_employees": severe_employees,
            "text_insufficient_count": text_insufficient_count,
        }

    # ── 步骤 1.3: LLM 语义理解 ──────────────────────────────────────

    def _process_employees(self, employees_df, perf_df, proj_df, eval_df, context
                           ) -> tuple[list[dict], dict]:
        """逐员工调用 LLM 生成文本摘要。"""
        trace_id = context.get("trace_id", "-")
        employee_ids = employees_df["employee_id"].tolist()
        total = len(employee_ids)
        summaries = []
        succeeded = 0
        failed = 0
        total_tokens = 0
        consecutive_failures = 0  # 用于指数退避

        for idx, emp_id in enumerate(employee_ids):
            if idx > 0 and idx % LLM_CANCEL_CHECK_INTERVAL == 0:
                if self._check_cancel(context):
                    logger.warning(
                        f"DataUnderstanding cancel_event 触发，停止于第 {idx}/{total} 员工",
                        extra={"trace_id": trace_id},
                    )
                    break

            emp_perf = perf_df[perf_df["employee_id"] == emp_id]
            emp_proj = proj_df[proj_df["employee_id"] == emp_id]
            emp_eval = eval_df[eval_df["employee_id"] == emp_id]

            perf_text = "；".join(emp_perf["performance_comment"].dropna().tolist())
            proj_text = "；".join(emp_proj["description"].dropna().tolist())
            eval_text = "；".join(emp_eval["comment"].dropna().tolist())

            record = {"employee_id": emp_id}

            if not perf_text and not proj_text and not eval_text:
                record["summary_error"] = "文本数据不足"
                record["text_summaries"] = None
                record["anchors"] = None
                summaries.append(record)
                failed += 1
                consecutive_failures += 1
                continue

            try:
                summary = self._summarize_employee(emp_id, perf_text, proj_text, eval_text)
            except Exception as e:
                logger.error(f"员工 {emp_id} LLM 调用异常: {e}", extra={"trace_id": trace_id})
                record["summary_error"] = f"API调用失败: {e}"
                record["text_summaries"] = None
                record["anchors"] = None
                summaries.append(record)
                failed += 1
                consecutive_failures += 1
                self._apply_backoff(consecutive_failures)
                continue

            if summary.get("error"):
                record["summary_error"] = summary["error"]
                record["text_summaries"] = None
                record["anchors"] = None
                failed += 1
                consecutive_failures += 1
                self._apply_backoff(consecutive_failures)
            else:
                content = summary.get("content")
                if not isinstance(content, dict):
                    if content is None:
                        content = {}
                    else:
                        record["summary_error"] = f"LLM 返回非 dict: {type(content).__name__}"
                        record["text_summaries"] = None
                        record["anchors"] = None
                        failed += 1
                        consecutive_failures += 1
                        self._apply_backoff(consecutive_failures)
                        summaries.append(record)
                        continue
                record["summary_error"] = None
                record["text_summaries"] = {
                    "performance_summary": content.get("performance_summary", ""),
                    "project_summary": content.get("project_summary", ""),
                    "evaluation_summary": content.get("evaluation_summary", ""),
                }
                record["anchors"] = content.get("anchors", {})

                # 锚点存在性验证
                record["anchor_mismatch"] = self._verify_anchors(
                    record["anchors"],
                    perf_text, proj_text, eval_text,
                )

                # 摘要长度合理性检查
                record["hallucination_flags"] = self._check_summary_lengths(
                    record["text_summaries"],
                    perf_text, proj_text, eval_text,
                )

                succeeded += 1
                consecutive_failures = 0  # 成功 → 重置失败计数
                total_tokens += (
                    summary.get("usage", {}).get("prompt_tokens", 0)
                    + summary.get("usage", {}).get("completion_tokens", 0)
                )

            summaries.append(record)
            time.sleep(LLM_CALL_SLEEP)

        stats = {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "total_tokens": total_tokens,
        }
        return summaries, stats

    def _summarize_employee(self, emp_id: str, perf_text: str,
                            proj_text: str, eval_text: str) -> dict:
        """对单员工调用 LLM 生成结构化摘要。

        委托给 utils.llm_summarizer.summarize_employee_texts，
        返回格式与原始 call_llm_json 结果兼容（_process_employees 依赖此格式）。
        """
        from utils.llm_summarizer import summarize_employee_texts

        result = summarize_employee_texts(emp_id, perf_text, proj_text, eval_text)

        if result.get("error"):
            return {
                "content": None,
                "error": result["error"],
                "usage": {},
                "model": result.get("model", ""),
            }

        return {
            "content": {
                "performance_summary": result["text_summaries"]["performance_summary"],
                "project_summary": result["text_summaries"]["project_summary"],
                "evaluation_summary": result["text_summaries"]["evaluation_summary"],
                "anchors": result["anchors"],
            },
            "error": None,
            "usage": result.get("usage", {}) or {},
            "model": result.get("model", ""),
        }

    # ── 指数退避 ──────────────────────────────────────────────

    @staticmethod
    def _apply_backoff(consecutive_failures: int) -> None:
        """递增退避：失败次数 × 2s，最大 15s。"""
        if consecutive_failures <= 0:
            return
        sleep_time = min(consecutive_failures * LLM_BACKOFF_BASE, LLM_BACKOFF_MAX)
        logger.info(f"指数退避 {sleep_time}s (连续失败 {consecutive_failures} 次)")
        time.sleep(sleep_time)

    # ── 锚点存在性验证 ─────────────────────────────────────────

    @staticmethod
    def _verify_anchors(anchors: dict, perf_text: str, proj_text: str,
                        eval_text: str) -> bool:
        """验证锚点是否在原文中出现。命中率 < 80% → 返回 True (有 mismatch)。"""
        if not anchors:
            return False

        text_map = {"performance": perf_text, "projects": proj_text, "evaluation": eval_text}
        total = 0
        hits = 0

        for key, anchor_list in anchors.items():
            if not isinstance(anchor_list, list):
                continue
            source_text = text_map.get(key, "")
            for anchor in anchor_list:
                if not isinstance(anchor, str) or not anchor.strip():
                    continue
                total += 1
                # 模糊匹配：允许 ±2 字差异 → 取 anchor[2:] 和 anchor[:-2] 范围
                trimmed = anchor.strip()
                if not trimmed:
                    continue
                if trimmed in source_text:
                    hits += 1
                elif len(trimmed) > 4 and trimmed[2:] in source_text:
                    hits += 1
                elif len(trimmed) > 4 and trimmed[:-2] in source_text:
                    hits += 1
                elif len(trimmed) > 4 and trimmed[1:-1] in source_text:
                    hits += 1

        if total == 0:
            return False
        hit_rate = hits / total
        return hit_rate < 0.8  # True = 存在 mismatch

    # ── 摘要长度合理性检查 ─────────────────────────────────────

    @staticmethod
    def _check_summary_lengths(summaries: dict, perf_text: str,
                               proj_text: str, eval_text: str) -> dict:
        """检查摘要是否显著长于原文。返回异常标记字典。"""
        if not summaries:
            return {}

        # 原文长度（字符数）
        original_lengths = {
            "performance": len(perf_text) if perf_text else 0,
            "projects": len(proj_text) if proj_text else 0,
            "evaluation": len(eval_text) if eval_text else 0,
        }

        # 摘要原文映射
        summary_to_key = {
            "performance_summary": "performance",
            "project_summary": "projects",
            "evaluation_summary": "evaluation",
        }

        flags = {}
        for summary_key, orig_key in summary_to_key.items():
            summary_text = summaries.get(summary_key, "")
            orig_len = original_lengths.get(orig_key, 0)
            summary_len = len(summary_text) if summary_text else 0

            if orig_len == 0 or summary_len == 0:
                if orig_len == 0 and summary_len > 0:
                    flags[summary_key] = "possible_hallucination"
                continue

            # 原文不足 30 字 → 摘要上限 = 原文 × 2
            if orig_len < 30:
                if summary_len > orig_len * 2:
                    flags[summary_key] = "possible_hallucination"
            elif summary_len > orig_len * 1.5:
                flags[summary_key] = "possible_hallucination"

        return flags

    # ── 步骤 1.4: 360 评价预处理 ────────────────────────────────────

    def _preprocess_360(self, eval_df: pd.DataFrame,
                        employees_df: pd.DataFrame) -> dict:
        """360 评价预处理：异常检测 + 角色权重 + 加权得分。

        算法：
        1. 计算全局均值 μ 和标准差 σ
        2. 对每个评价者计算个人评分均值
        3. |μ_evaluator - μ_global| > 2σ → 标记异常 → 权重 ×0.2
        4. 角色权重加权 → 每员工×每维度的加权得分
        """
        # 第 1 步：全局统计量
        all_scores = eval_df["score"].dropna()
        if len(all_scores) == 0:
            return {"_summary": {"error": "无可用评分"}, "_evaluators_skipped": 0}

        global_mean = all_scores.mean()
        global_std = all_scores.std()

        # 第 2 步：评价者均值
        evaluator_means = (
            eval_df.groupby("evaluator_id")["score"]
            .agg(["mean", "count"])
            .reset_index()
        )

        # 第 3 步：异常检测
        anomalous_evaluators = set()
        evaluators_skipped = 0
        for _, row in evaluator_means.iterrows():
            if row["count"] < EVALUATOR_MIN_SAMPLE_SIZE:
                evaluators_skipped += 1
                continue
            deviation = abs(row["mean"] - global_mean)
            if deviation > 2 * global_std:
                anomalous_evaluators.add(row["evaluator_id"])

        # 员工 → 岗位类型映射
        emp_job_type = dict(zip(
            employees_df["employee_id"].astype(str),
            employees_df.get("job_sequence", "技术研发类").astype(str),
        ))

        # 第 4 步：角色权重加权
        result = {}
        employee_ids = eval_df["employee_id"].unique()

        for emp_id in employee_ids:
            emp_data = eval_df[eval_df["employee_id"] == emp_id]
            job_type = emp_job_type.get(emp_id, "技术研发类")

            role_weights = dict(ROLE_WEIGHTS_BASELINE)
            adj = ROLE_ADJUSTMENTS.get(job_type, {})
            for role, delta in adj.items():
                if role in role_weights:
                    role_weights[role] = round(role_weights[role] + delta, 4)

            # 同角色 ≥5 人 → 权重上调 5 个百分点
            role_counts = emp_data[emp_data["evaluator_role"] != SELF_ROLE] \
                .groupby("evaluator_role")["evaluator_id"].nunique()
            for role, count in role_counts.items():
                if count >= 5 and role in role_weights:
                    role_weights[role] = round(role_weights[role] + 0.05, 4)

            dims = emp_data["dimension"].unique()
            emp_scores = {}
            for dim in dims:
                dim_data = emp_data[emp_data["dimension"] == dim]
                weighted_sum = 0.0
                weight_total = 0.0

                for _, row in dim_data.iterrows():
                    role = row["evaluator_role"]
                    score = row["score"]
                    if pd.isna(score):
                        continue
                    if role == SELF_ROLE:
                        continue

                    base_w = role_weights.get(role)
                    if base_w is None:
                        continue

                    penalty = 0.2 if row["evaluator_id"] in anomalous_evaluators else 1.0
                    final_w = base_w * penalty
                    weighted_sum += score * final_w
                    weight_total += final_w

                emp_scores[dim] = round(float(weighted_sum / weight_total), 4) if weight_total > 0 else None

            for dim in KNOWN_DIMENSIONS:
                if dim not in emp_scores:
                    emp_scores[dim] = None

            result[emp_id] = emp_scores

        result["_summary"] = {
            "global_mean": round(float(global_mean), 4),
            "global_std": round(float(global_std), 4),
            "anomalous_evaluators": len(anomalous_evaluators),
            "evaluators_skipped_low_sample": evaluators_skipped,
        }
        result["_evaluators_skipped"] = evaluators_skipped
        return result

    # ── 步骤 1.5: 融合输出 ──────────────────────────────────────────

    def _merge_records(self, employees_df, perf_df, proj_df, train_df,
                       summaries, scores_360, data_quality) -> list[dict]:
        """融合所有数据源为每员工一条记录的列表。"""
        score_keys = {k: v for k, v in scores_360.items() if not k.startswith("_")}
        summary_map = {s["employee_id"]: s for s in summaries}

        records = []
        for _, emp in employees_df.iterrows():
            emp_id = str(emp["employee_id"])

            structured = {
                "name": self._safe_val(emp, "name"),
                "age": self._safe_val(emp, "age", 0),
                "gender": self._safe_val(emp, "gender"),
                "education": self._safe_val(emp, "education"),
                "major": self._safe_val(emp, "major"),
                "job_sequence": self._safe_val(emp, "job_sequence"),
                "current_position": self._safe_val(emp, "current_position"),
                "current_level": self._safe_val(emp, "current_level"),
                "years_of_service": self._safe_val(emp, "years_of_service", 0),
            }

            emp_perf = perf_df[perf_df["employee_id"] == emp_id]
            perf_records = []
            for _, p in emp_perf.iterrows():
                yr = p.get("year")
                perf_records.append({
                    "year": int(yr) if pd.notna(yr) else None,
                    "grade": str(p.get("performance_grade", "")),
                    "comment": str(p.get("performance_comment", "")),
                })

            emp_proj = proj_df[proj_df["employee_id"] == emp_id]
            proj_records = []
            for _, p in emp_proj.iterrows():
                tools = p.get("tools_used", [])
                if isinstance(tools, str):
                    try:
                        tools = json.loads(tools)
                    except (json.JSONDecodeError, TypeError):
                        tools = [tools]
                tools = tools if isinstance(tools, list) else []
                proj_records.append({
                    "project_name": str(p.get("project_name", "")),
                    "role": str(p.get("role", "")),
                    "tools": tools,
                    "description": str(p.get("description", "")),
                })

            emp_train = train_df[train_df["employee_id"] == emp_id]
            train_records = []
            for _, t in emp_train.iterrows():
                score = t.get("score")
                train_records.append({
                    "course_name": str(t.get("course_name", "")),
                    "status": str(t.get("status", "")),
                    "score": int(score) if pd.notna(score) and score != "" else None,
                })

            s = summary_map.get(emp_id, {})
            text_summaries = s.get("text_summaries")
            anchors = s.get("anchors")
            summary_error = s.get("summary_error")
            anchor_mismatch = s.get("anchor_mismatch", False)
            hallucination_flags = s.get("hallucination_flags", {})

            scores = score_keys.get(emp_id, {})
            is_severe = emp_id in data_quality.get("severe_missing_employees", [])

            record = {
                "employee_id": emp_id,
                "structured": structured,
                "performance": perf_records,
                "projects": proj_records,
                "training": train_records,
                "text_summaries": text_summaries,
                "scores_360": scores,
                "anchors": anchors,
                "anchor_mismatch": anchor_mismatch,
                "hallucination_flags": hallucination_flags,
                "data_quality_flags": {
                    "missing_rate": None,
                    "text_sufficient": text_summaries is not None,
                    "severe_missing": is_severe,
                    "summary_error": summary_error,
                },
            }
            records.append(record)

        return records

    @staticmethod
    def _safe_val(row: pd.Series, col: str, default=None):
        """安全地从 Pandas Series 读取值，NaN/NA 转为 default。"""
        val = row.get(col)
        # None / np.nan / pd.NA / pd.NaT 统一处理
        if val is None or (isinstance(val, (float, np.floating)) and np.isnan(val)):
            return default
        if isinstance(val, type(pd.NA)):
            return default
        if isinstance(val, (np.integer,)):
            return int(val)
        if isinstance(val, (np.floating,)):
            return float(val)
        return val
