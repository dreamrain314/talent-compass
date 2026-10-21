"""员工证据向量索引（M1，向量直配匹配层召回地基）。

设计（竞品 TalentAtlas 思路迁移，docs/competitor_talentatlas_analysis.md）：
召回不依赖 LLM 单次抽取的标签——那是 87% miss 的来源（plan_t1_optimization
归因回放）——而是把员工多源证据按记录自然切片（chunk）直接入向量空间，
岗位要求以向量检索找人。T1 标签降级为展示/解释层。

- chunk：一条绩效评语 / 一个项目 / 一条培训 / 一段摘要 / 岗位证书行 = 1 chunk，
  带 {emp_id, source, text, anchor} 元数据；anchor 沿用 Agent① 的锚点语义，
  供 Agent④ 证据链点回原文。
- 编码：复用 utils/label_embedding 的 fastembed bge-small-zh 单例 + LRU 缓存
  （encode_labels(encode_fn=None) 真实路径；测试注入确定性 fake）。
- 检索：query 向量 × chunk 矩阵余弦（矩阵语义同 _cosine_batch，向量化实现）。
- 缓存：.npy 持久化，键 = md5(model + 全部 chunk 文本)。命中且哈希一致 → 免重编。

消费者：agents/matching.py（M3 匹配引擎）、scripts/blind_test.py（M4 盲测）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

import config
from utils.label_embedding import encode_labels

__all__ = ["chunk_employee", "build_evidence_chunks", "EvidenceIndex"]

# 绩效等级序数（与 config.PERFORMANCE_ORDINAL 同语义；这里用于轨迹文本，
# 不做数值比较，独立小写映射即可）
_GRADE_TEXT = {"A": "优秀A", "B": "良好B", "C": "合格C", "D": "待改进D"}


def _clip(text: str, limit: int | None = None) -> str:
    """截断到上限（None→config.EVIDENCE_CHUNK_MAX_CHARS），防御超长摘要稀释向量。"""
    limit = config.EVIDENCE_CHUNK_MAX_CHARS if limit is None else limit
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def chunk_employee(emp: dict) -> list[dict]:
    """把一名员工的多源证据切成 chunk 列表（确定性，零 LLM）。

    来源与优先级（与 Agent① phase1_output 字段一一对应）：
    - position：structured 岗位/专业/证书摘要行（1 chunk）
    - projects：每个项目 1 chunk（名称+角色+工具+描述）
    - performance：每年绩效 1 chunk（等级+评语）
    - training：每条培训 1 chunk（课程名+成绩）
    - text_summaries：三段摘要各 1 chunk（performance/project/evaluation）

    Args:
        emp: Agent① 输出的员工记录（employee_id/structured/projects/performance/
            training/text_summaries）。

    Returns:
        [{emp_id, source, text, anchor}]，字段类型恒定（C1 对称契约）。
        anchor 取 chunk 文本前 10 字（config.PLACEHOLDER_ANCHOR_LEN 语义）。
    """
    emp_id = str(emp.get("employee_id", ""))
    chunks: list[dict] = []

    def _add(source: str, text: str) -> None:
        text = _clip(text)
        if not text:
            return
        anchor = text[: config.PLACEHOLDER_ANCHOR_LEN]
        chunks.append({"emp_id": emp_id, "source": source, "text": text, "anchor": anchor})

    # 1. 岗位/专业/证书结构化行（T0 直接技能的命中池之一）
    structured = emp.get("structured") or {}
    if isinstance(structured, dict):
        parts = []
        position = structured.get("current_position") or ""
        major = structured.get("major") or ""
        certs = structured.get("certificates") or ""
        seq = structured.get("job_sequence") or ""
        if position:
            parts.append(f"岗位：{position}")
        if seq:
            parts.append(f"序列：{seq}")
        if major:
            parts.append(f"专业：{major}")
        if certs and certs != "无":
            parts.append(f"证书：{certs}")
        _add("position", "；".join(parts))

    # 2. 项目（T1 语义匹配的主力证据）
    projects = emp.get("projects") or []
    if isinstance(projects, list):
        for p in projects:
            if not isinstance(p, dict):
                continue
            name = p.get("project_name") or ""
            role = p.get("role") or ""
            tools = p.get("tools") or []
            desc = p.get("description") or ""
            if not (name or desc):
                continue
            tool_str = "/".join(str(t) for t in tools if t) if isinstance(tools, list) else ""
            line = f"项目「{name}」角色：{role}"
            if tool_str:
                line += f"；工具：{tool_str}"
            if desc:
                line += f"；{desc}"
            _add("projects", line)

    # 3. 绩效（每年 1 条，含等级与评语）
    performance = emp.get("performance") or []
    if isinstance(performance, list):
        for pr in performance:
            if not isinstance(pr, dict):
                continue
            year = pr.get("year") or ""
            grade = pr.get("grade") or ""
            comment = pr.get("comment") or ""
            if not (grade or comment):
                continue
            _add("performance", f"{year}年绩效{_GRADE_TEXT.get(grade, grade)}：{comment}")

    # 4. 培训（课程名+状态+成绩，T0 命中池之一）
    training = emp.get("training") or []
    if isinstance(training, list):
        for t in training:
            if not isinstance(t, dict):
                continue
            course = t.get("course_name") or ""
            if not course:
                continue
            status = t.get("status") or ""
            score = t.get("score")
            line = f"培训：{course}"
            if status:
                line += f"（{status}）"
            if isinstance(score, (int, float)) and score:
                line += f" 成绩{int(score)}"
            _add("training", line)

    # 5. 三段文本摘要（evaluation_summary 是 360 评语聚合，T2 行为证据主力）
    summaries = emp.get("text_summaries") or {}
    if isinstance(summaries, dict):
        _add("summary_performance", summaries.get("performance_summary") or "")
        _add("summary_project", summaries.get("project_summary") or "")
        _add("summary_evaluation", summaries.get("evaluation_summary") or "")

    return chunks


def build_evidence_chunks(employees: list[dict]) -> list[dict]:
    """全员 chunk 拼接（chunk_employee 的批量包装）。"""
    all_chunks: list[dict] = []
    for emp in employees or []:
        all_chunks.extend(chunk_employee(emp))
    return all_chunks


class EvidenceIndex:
    """员工证据 chunk 向量索引（内存矩阵 + 可选 .npy 持久缓存）。

    用法：
        idx = EvidenceIndex.build(employees)          # 首次编码
        hits = idx.search("雷达微多普勒分析", top_k=5)  # chunk 级检索
        scores = idx.employee_scores(queries, emp_ids) # 人级聚合（max-pool→mean）
    """

    def __init__(self, chunks: list[dict], matrix: np.ndarray, encode_fn=None):
        self.chunks = chunks
        self.matrix = matrix  # (N, dim) 或 (0,) 空
        # 索引对自己的编码器负责：构建用哪个编码器，检索默认也用它
        # （防 fake 注入构建 / 真实模型检索的维度错配）
        self.encode_fn = encode_fn

    # ── 构建 ────────────────────────────────────────────────
    @classmethod
    def build(
        cls,
        employees: list[dict],
        encode_fn=None,
        cache_path: str | Path | None = None,
    ) -> "EvidenceIndex":
        """构建索引。

        Args:
            employees: Agent① 输出员工列表。
            encode_fn: 编码函数 list[str]->array（测试注入确定性 fake）；
                None→encode_labels 真实路径（fastembed + LRU）。
            cache_path: .npy 缓存路径；None→不读不写缓存（测试/一次性场景）。
                命中条件：文件存在且内嵌哈希与当前 chunks 一致，否则重编并覆写。
        """
        chunks = build_evidence_chunks(employees)
        texts = [c["text"] for c in chunks]

        expected_hash = cls._hash(chunks)

        if cache_path is not None and not texts:
            return cls(chunks, np.array([]))

        if cache_path is not None:
            cached = cls._try_load_cache(cache_path, expected_hash, len(chunks))
            if cached is not None:
                return cls(chunks, cached, encode_fn=encode_fn)

        matrix = encode_labels(texts, encode_fn=encode_fn) if texts else np.array([])

        if cache_path is not None:
            cls._save_cache(cache_path, expected_hash, matrix)
        return cls(chunks, matrix, encode_fn=encode_fn)

    @staticmethod
    def _hash(chunks: list[dict]) -> str:
        payload = json.dumps(
            [config.EMBEDDING_MODEL_NAME] + [c["text"] for c in chunks],
            ensure_ascii=False,
        )
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _try_load_cache(path: str | Path, expected_hash: str, n_chunks: int):
        """读 .npy 缓存。哈希编入文件名（{stem}_{hash}.npy），避免 object dtype
        与 allow_pickle 纠缠；形状不符/损坏 → None（回退重编）。"""
        p = Path(path)
        target = p.with_name(f"{p.stem}_{expected_hash}.npy")
        if not target.exists():
            return None
        try:
            data = np.load(target, allow_pickle=False)
            if data.ndim != 2 or data.shape[0] != n_chunks:
                return None
            return np.asarray(data, dtype=float)
        except Exception:
            return None

    @staticmethod
    def _save_cache(path: str | Path, h: str, matrix: np.ndarray) -> None:
        """写 .npy 缓存（float 矩阵，文件名带哈希）并清理同 stem 旧哈希文件。
        失败静默（缓存非关键路径）。"""
        try:
            if matrix.size == 0:
                return
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            target = p.with_name(f"{p.stem}_{h}.npy")
            np.save(target, np.asarray(matrix, dtype=np.float32))
            for old in p.parent.glob(f"{p.stem}_*.npy"):
                if old != target:
                    old.unlink(missing_ok=True)
        except Exception:
            pass

    # ── 检索 ────────────────────────────────────────────────
    def _query_matrix(self, queries: list[str], encode_fn=None) -> np.ndarray:
        fn = encode_fn if encode_fn is not None else self.encode_fn
        qvecs = encode_labels(queries, encode_fn=fn) if queries else np.array([])
        if qvecs.size == 0:
            return np.array([])
        if qvecs.ndim == 1:
            qvecs = qvecs.reshape(1, -1)
        return qvecs

    def search(self, query: str, top_k: int = 5, encode_fn=None) -> list[dict]:
        """chunk 级检索：单 query → 相似度 top-K chunk（带 sim 字段）。"""
        if self.matrix.size == 0 or self.matrix.ndim != 2 or not (query or "").strip():
            return []
        q = self._query_matrix([query], encode_fn=encode_fn)
        if q.size == 0:
            return []
        sims = self._cosine(q[0], self.matrix)
        k = min(top_k, len(sims))
        if k <= 0:
            return []
        order = np.argsort(-sims)[:k]
        return [{**self.chunks[i], "sim": float(sims[i])} for i in order]

    def employee_scores(
        self, queries: list[str], emp_ids: list[str] | None = None, encode_fn=None
    ) -> dict[str, float]:
        """人级聚合分：每 query 对每员工取其 chunk 最高 sim（max-pool），
        再对 queries 取均匀 mean → {emp_id: score(0-1)}。

        Args:
            queries: 岗位要求文本列表（通常已用标签库 definition 富化）。
            emp_ids: 限定聚合的员工集合；None→索引内全部员工。
        """
        if self.matrix.size == 0 or self.matrix.ndim != 2 or not queries:
            return {}
        qvecs = self._query_matrix(queries, encode_fn=encode_fn)
        if qvecs.size == 0:
            return {}
        # (Q, N) 相似度矩阵
        sims = self._cosine_matrix(qvecs, self.matrix)
        emp_of_chunk = np.array([c["emp_id"] for c in self.chunks])
        target_ids = set(emp_ids) if emp_ids is not None else set(emp_of_chunk.tolist())
        scores: dict[str, float] = {}
        # 逐 query max-pool：对每个员工取其 chunk 的最大 sim
        per_query_emp_max: list[dict[str, float]] = []
        for qi in range(sims.shape[0]):
            emp_max: dict[str, float] = {}
            row = sims[qi]
            order = np.argsort(-row)
            # 倒序扫描，首次遇到某员工即为其最大值
            for ci in order:
                eid = emp_of_chunk[ci]
                if eid in target_ids and eid not in emp_max:
                    emp_max[eid] = float(row[ci])
            per_query_emp_max.append(emp_max)
        for eid in target_ids:
            vals = [m.get(eid, 0.0) for m in per_query_emp_max]
            scores[eid] = float(np.mean(vals)) if vals else 0.0
        return scores

    def top_chunks_for_employee(
        self, query: str, emp_id: str, top_k: int = 3, encode_fn=None
    ) -> list[dict]:
        """某员工在单 query 下的 top-K chunk（证据链素材）。"""
        if self.matrix.size == 0 or self.matrix.ndim != 2:
            return []
        q = self._query_matrix([query], encode_fn=encode_fn)
        if q.size == 0:
            return []
        sims = self._cosine(q[0], self.matrix)
        idxs = [i for i, c in enumerate(self.chunks) if c["emp_id"] == emp_id]
        idxs.sort(key=lambda i: -sims[i])
        return [
            {**self.chunks[i], "sim": float(sims[i])} for i in idxs[:top_k]
        ]

    # ── 余弦（零向量→0，语义同 label_embedding._cosine_batch）──
    @staticmethod
    def _cosine(q: np.ndarray, m: np.ndarray) -> np.ndarray:
        qn = np.linalg.norm(q) or 1.0
        mn = np.linalg.norm(m, axis=1)
        denom = mn * qn
        sims = (m @ q) / np.where(denom == 0, 1.0, denom)
        return np.nan_to_num(sims, nan=0.0, posinf=0.0, neginf=0.0)

    @classmethod
    def _cosine_matrix(cls, qvecs: np.ndarray, m: np.ndarray) -> np.ndarray:
        qn = np.linalg.norm(qvecs, axis=1, keepdims=True)
        qn = np.where(qn == 0, 1.0, qn)
        mn = np.linalg.norm(m, axis=1)
        mn = np.where(mn == 0, 1.0, mn)
        sims = (qvecs @ m.T) / mn[None, :]
        sims = sims / np.where(qn == 0, 1.0, qn)
        return np.nan_to_num(sims, nan=0.0, posinf=0.0, neginf=0.0)
