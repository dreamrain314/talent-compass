# 源码摘录文档：SkillNer / Skill-LLM 可复用模式提取（供 talent-compass T1 优化参考）

> **提取角色**：角色B 源码提取员（工作流 fan-out） ｜ **日期**：2026-09-09
> **许可总览**：SkillNer = MIT（README 徽章确认，可改可抄需保留版权声明）；Skill-LLM（herandy fork）= **无许可证：仅作模式参考，禁止逐字复制到我们的代码**
> **配套文档**：`docs/competitive_research_skill_extraction.md`（调研结论）、计划文档（角色A 产出，另行落盘）

**抓取执行记录**

| # | 源 | 状态 |
|---|---|---|
| 1 | `skillNer/matcher_class.py` | 全文 OK |
| 2 | `skillNer/general_params.py` | 全文 OK（比预期小：SKILL_DB 运行时从 `skill_db_relax_20.json` 加载，非内联） |
| 3 | `skillNer/utils.py` | 全文 OK |
| 4 | Skill-LLM `src/` 目录列表 + `data_preparation.sh` | OK，据此选中 preprocessing/postprocessing 共 3 个 .py（任务要求 1-2，超额） |
| - | `postprocessing/gliner_model.py` | webReader 网络错误 1 次，材料已足，跳过（非任务必需） |
| - | WebFetch 对 raw.githubusercontent.com 域名验证失败 1 次 | 按指令直接切 webReader，未纠结 |

结论：4 项指定目标全部完成，**无需标 [PARTIAL]**。

---

## 摘录 1：多形态别名匹配器注册表（SkillNer `matcher_class.py`）

**来源**：https://raw.githubusercontent.com/AnasAito/SkillNER/master/skillNer/matcher_class.py ｜ **许可证**：MIT

**关键代码**（`matcher_class.py`，`Matchers.__init__` 约第 29-45 行 + 各 getter 约第 100-190 行 + `SkillsGetter` 约第 230-250 行，压缩摘录）：

```python
self.dict_matcher = {
    'full_matcher': self.get_full_matcher,        # 高置信: 多词技能全称
    'abv_matcher': self.get_abv_matcher,          # 高置信: 缩写 (如 ML)
    'full_uni_matcher': self.get_full_uni_matcher,# 高置信: 单词技能
    'low_form_matcher': self.get_low_form_matcher,# 低置信: 变体/屈折形式
    'token_matcher': self.get_token_matcher,      # 低置信: 单 token 命中
}

def get_full_matcher(self):
    full_matcher = self.phraseMatcher(nlp.vocab, attr="LOWER")
    for key in skills_db:
        skill_len = skills_db[key]['skill_len']
        if skill_len > 1:
            skill_full_name = skills_db[key]['high_surfce_forms']['full']
            full_matcher.add(str(key), [nlp.make_doc(skill_full_name)])
    return full_matcher

def get_abv_matcher(self):
    abv_matcher = self.phraseMatcher(nlp.vocab, attr="LOWER")
    for key in skills_db:
        if 'abv' in skills_db[key]['high_surfce_forms'].keys():   # 可选字段守卫
            abv_matcher.add(str(key), [nlp.make_doc(skills_db[key]['high_surfce_forms']['abv'])])
    return abv_matcher

def get_low_form_matcher(self):
    low_form_matcher = self.phraseMatcher(nlp.vocab, attr="LOWER")
    for key in skills_db:
        for form in skills_db[key]['low_surface_forms']:  # 低置信变体全量入 matcher
            low_form_matcher.add(str(key), [nlp.make_doc(form)])
    return low_form_matcher

# SkillsGetter: 命中后将 token 抢占, 防止被低置信通道重复消费
for match_id, start, end in matcher(doc):
    skills.append({'skill_id': id_, 'doc_node_value': str(doc[start:end]),
                   'score': 1, 'doc_node_id': list(range(start, end))})
    for token in text_obj[start:end]:
        token.is_matchable = False
```

**映射瓶颈**：**B2 间接映射**（ISO9001→质量工程）。核心可复用思想：别名不是平铺一张 `alias→label` 表，而是按**置信度分级的多 matcher 管线**——标准全称（高置信，直接进 items）、缩写（高置信）、变体/口语形式（低置信，进 candidates 待 LLM/评分裁决）；且高置信命中先**抢占 token**（`is_matchable=False`），低置信通道只能吃剩余。这正是「ISO9001」这类证书词映射到「质量工程」概念时需要的结构：ISO9001 放 `low_surface_forms`（或专门的 `indirect_forms` 档），命中后作为 candidate 而非直接定 label。

**中文化伪代码**（对齐我们契约：对称顶层 key + `isinstance` 入口守卫）：

```python
# concept_db: standard_label 为主键(对应 skill_id, 天然消重)
CONCEPT_DB: dict[str, dict] = {
    "质量工程": {
        "concept_len": 4,
        "high_surface_forms": {"full": "质量管理工程", "abv": "TQM"},
        "low_surface_forms": ["ISO9001体系", "iso9001认证", "质量体系认证"],  # B2 间接词
        "match_on_tokens": False,
    },
    "Python开发": {"high_surface_forms": {"full": "Python开发"}, "low_surface_forms": ["py开发"], ...},
}

def build_matchers(nlp, concept_db: dict) -> dict:
    """返回 {'full': PhraseMatcher, 'low': PhraseMatcher}; attr 用 NORM 做全半角归一"""
    full, low = ..., ...
    for std_label, meta in concept_db.items():
        if meta.get("concept_len", 1) > 1:
            full.add(std_label, [nlp.make_doc(meta["high_surface_forms"]["full"])])
        for alias in meta.get("low_surface_forms", []):
            low.add(std_label, [nlp.make_doc(alias)])
    return {"full": full, "low": low}

def match_concepts(text: str) -> dict:
    # return 路径 key 集合: {ok, items, error} (3 条路径一致)
    if not isinstance(text, str):
        return {"ok": False, "items": [], "error": f"type error: expected str, got {type(text).__name__}"}
    if not text.strip():
        return {"ok": True, "items": [], "error": None}
    taken = set()                       # token 抢占集合(替代 is_matchable 变异)
    items = []
    for i, (label, span, mtype, score) in enumerate(run_matchers(text, taken)):
        taken.update(range(span.start, span.end))
        items.append({"idx": i, "concept": span.text,
                      "standard_label": label if mtype == "high" else None,
                      "candidates": [{"label": label, "score": score}] if mtype == "low" else []})
    return {"ok": True, "items": items, "error": None}
```

- **抄什么**：多级 matcher 注册表结构（dict_matcher + include/exclude 管线）、`low_surface_forms` 作为间接映射词槽位、token 抢占防重复消费、`'abv' in dict` 可选字段守卫。
- **改什么**：attr="LOWER" 换中文归一（全半角/简繁）；skill_id 换成 standard_label 主键；变体生成（英文屈折 stemming）换中文别名人工+LLM 辅助维护。
- **扔什么**：spaCy 英文依赖（en_core_web_lg）、abv_text/lemmed 多文本通道（中文无屈折）、`token.isdigit(): pass` 之外的英文 token 处理细节。

---

## 摘录 2：SKILL_DB schema + 冗余短语停用表（SkillNer `general_params.py`）

**来源**：https://raw.githubusercontent.com/AnasAito/SkillNER/master/skillNer/general_params.py ｜ **许可证**：MIT

**关键代码**（第 1-60 行；SKILL_DB 本体在 `skill_db_relax_20.json`，schema 由 `matcher_class.py` 消费方式 + README 输出示例还原）：

```python
# 本地 json 优先, 缺失则远程拉取并落盘
try:
    with open('skill_db_relax_20.json') as json_file:
        SKILL_DB = json.load(json_file)
except:
    SKILL_DB = bucket.fetch_remote("SKILL_DB")
    with open('skill_db_relax_20.json', 'w') as fp:
        json.dump(SKILL_DB, fp)

# SKILL_DB 单条 schema(还原):
# { "KS122Z36QK3N5097B5JH": {              # skill_id: EMSI 主键, 消重锚点
#     "skill_len": 2,                       # >1 进 full_matcher, ==1 进 full_uni_matcher
#     "skill_type": "Hard Skill",           # Hard/Soft/Certification 三分类
#     "high_surfce_forms": {"full": "web development", "abv": "wd"},
#     "low_surface_forms": ["web dev"],
#     "match_on_tokens": false } }
# README 输出示例:
# {'skill_id': 'KS122Z36QK3N5097B5JH', 'doc_node_value': 'web development',
#  'score': 1, 'doc_node_id': [10, 11]}

# 冗余短语停用表(截选): 模式像技能但不是技能的 n-gram
S_GRAM_REDUNDANT = ['of the', 'experience in', 'ability to', 'knowledge of',
                    'at least', 'years of', 'or equivalent', 'professional experience',
                    'good knowledge', 'degree in', 'team spirit', 'fluency in', ...]
```

**映射瓶颈**：**B2 词汇/别名匹配结构**。两个直接可用的资产：(1) SKILL_DB 的**五字段 schema**（len 分流 + 高低双 surface_forms + match_on_tokens 开关）就是我们 concept_db 的目标形态；(2) `S_GRAM_REDUNDANT` 冗余短语表——中文简历里「相关工作经验」「年以上」「者优先」「具备良好」这类伪概念同样需要一张停用表，且它证明了**负向资产（不该命中的清单）与正向词典同等重要**（对应我们「负向断言」纪律）。

**中文化伪代码**：

```python
# 副作用矩阵提示: SkillNer 的"读模块顶层写 json"是反面教材——import 即落盘。
# 我们必须把加载放显式函数, 快速退出路径零写入(对照零落盘不变量)。
CN_REDUNDANT_GRAMS = ["相关工作经验", "年以上工作经验", "者优先", "具备良好的",
                      "熟练程度", "工作责任心", "相关领域", "岗位职责要求"]

def load_concept_db(path: str) -> dict:
    # return key 集合: {ok, db, error}
    if not isinstance(path, str):
        return {"ok": False, "db": {}, "error": f"type error: expected str, got {type(path).__name__}"}
    try:
        with open(path, encoding="utf-8") as f:
            db = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "db": {}, "error": f"load failed: {e}"}
    for label, meta in db.items():        # 基类兜底注入默认值, 不靠数据文件自觉
        meta.setdefault("concept_len", len(meta["high_surface_forms"]["full"]))
        meta.setdefault("low_surface_forms", [])
        meta.setdefault("match_on_tokens", False)
    return {"ok": True, "db": db, "error": None}
```

- **抄什么**：五字段 schema（skill_len 分流、high/low surface_forms、match_on_tokens 开关）、冗余短语停用表思路。
- **改什么**：停用表全量重写为中文语料；加载改显式函数+默认值兜底注入（CLAUDE.md §2 基类注入原则）。
- **扔什么**：import 即落盘的反模式（违反我们零落盘不变量）、EMSI skill_id 体系、颜色映射（SKILL_TO_COLOR）。

---

## 摘录 3：n-gram 冲突消解与邻接聚类（SkillNer `utils.py::process_n_gram`）

**来源**：https://raw.githubusercontent.com/AnasAito/SkillNER/master/skillNer/utils.py ｜ **许可证**：MIT

**关键代码**（`Utils.process_n_gram`，约第 175-240 行，压缩摘录）：

```python
def process_n_gram(self, matches, text_obj):
    if len(matches) == 0:
        return matches
    text_tokens = text_obj.lemmed(as_list=True)
    len_ = len(text_tokens)
    corpus, look_up = self.get_corpus(text_tokens, matches)   # 概念×token 0/1 矩阵
    corpus_csr = csr_matrix(corpus)
    co_occ_csr = corpus_csr.T.dot(corpus_csr)                 # token 共现矩阵
    clusters = self.get_clusters(co_occ_csr)                  # 共现 token 聚成 span
    ones = [self.make_one(cluster, len_) for cluster in clusters]  # span one-hot
    spans_conflicts = [(np.array(one),                        # 每个 span 上互相冲突的概念集
        np.array([a_[0] for a_ in np.argwhere(corpus_csr.dot(one) != 0)])) for one in ones]
    new_spans = []
    for span, skill_ids in spans_conflicts:
        span_scored_skills = [self.retain(text_obj, span, sk_id, look_up, corpus)
                              for sk_id in skill_ids]         # 逐候选打分
        types = [s['type'] for s in span_scored_skills]
        scores = [s['score'] for s in span_scored_skills]
        lens = [s['len'] for s in span_scored_skills]
        if 'oneToken' in types and len(set(types)) > 1:
            id_ = np.array(scores).argmax()
            max_score = 0.5  # selection treshold
            for i, len_ in enumerate(lens):                   # ⚠ 原码变量遮蔽 bug, 见下
                if len_ > 1 and types[i] == 'oneToken':
                    if scores[i] >= max_score:
                        id_ = i            # 长匹配可顶替, 但须越过 0.5 阈值
            new_spans.append(span_scored_skills[id_])
        else:
            new_spans.append(span_scored_skills[np.array(scores).argmax()])
    return new_spans
```

**映射瓶颈**：**S8 抽取后扩展步骤**（邻接/冲突消解）。可复用的算法骨架：把全部候选命中投成 `概念×token` 0/1 矩阵 → 转置相乘得 token 共现 → 共现聚类天然切出「冲突 span」→ 每个 span 内多候选打分择一。**关键裁决规则**：「长匹配默认赢，但必须越过 0.5 阈值才可顶替短匹配的高分」——与我们已知的 `skill_extractor_class.annotate` 双通道 `tresh=0.5` 一致，说明 0.5 是全库统一裁决阈值。`retain()` 里的 `compute_w_ratio` 还有「靠前 token 加权、靠后 token 罚 0.1」的位置先验，可迁移为「概念别名靠前词更重要」。

**中文化伪代码**：

```python
def resolve_span_conflicts(items: list, tokens: list) -> dict:
    # return key 集合: {ok, items, error} (3 条路径一致)
    if not isinstance(items, list):
        return {"ok": False, "items": [], "error": f"type error: expected list, got {type(items).__name__}"}
    if not items:
        return {"ok": True, "items": [], "error": None}
    corpus, look_up = build_bin_matrix(items, tokens)     # 候选概念 × token
    spans = cluster_by_cooccurrence(corpus)               # 共现 → 冲突 span
    resolved = []
    for span in spans:
        cand = [score_candidate(c, span, corpus, look_up) for c in span.candidates]
        pick = max(cand, key=lambda c: c["score"])
        if any(c["len"] > 1 and c["kind"] == "partial" for c in cand):
            long_c = max((c for c in cand if c["len"] > 1), key=lambda c: c["score"])
            if long_c["score"] >= PARTIAL_REPLACE_TRESH:  # 常量 0.5, 单点定义
                pick = long_c                              # 长匹配顶替, 须越阈值
        resolved.append(pick)
    out = [{"idx": i, "concept": p["text"], "standard_label": p["label"],
            "candidates": [c["label"] for c in span_loser_labels(p)]} for i, p in enumerate(resolved)]
    return {"ok": True, "items": out, "error": None}
```

- **抄什么**：0/1 矩阵→共现聚类→span 冲突→择优的骨架；「长匹配顶替须越 0.5 阈值」裁决规则；靠前 token 位置加权。
- **改什么**：csr_matrix 换 numpy 即可（中文简历文本短，稀疏优化过度）；打分函数 `retain` 的三分支（oneToken/fullUni/lowSurf）换成我们的 candidates 结构。
- **扔什么**：原代码有**变量遮蔽 bug**（`for i, len_ in enumerate(lens)` 覆盖外层 `len_`），照抄即埋雷——重命名后使用；jellyfish/jaro 英文编辑距离 fallback 换中文相似度（如字符 bigram Jaccard）。

---

## 摘录 4：skill_span+context 双锚点输出格式与 prompt 模板（Skill-LLM `prepare_data.py`）

**来源**：https://raw.githubusercontent.com/herandy/Skill-LLM/master/src/preprocessing/prepare_data.py（入口：`src/data_preparation.sh`）｜ **许可证**：**无许可证：仅作模式参考，禁止逐字复制到我们的代码**

**关键代码**（模块级 `INSTRUCTION_PROMPT` + `label_and_context_list_data()` 核心，约第 19-105 行，压缩摘录）：

```python
INSTRUCTION_PROMPT = [
    "You are a helpful information extraction system. Your job is to extract skill entities and knowledge entities from the given sentence.",
    "Your job is to extract skills and knowledge from given text.",
]   # 多条 instruction 随机轮换 → 提升泛化, 防 prompt 过拟合单一措辞

for index in tqdm(range(self.annotation_data.shape[0])):
    text, spans, tokens = data_entry.text, data_entry.spans, data_entry.tokens
    prompt_entry = {"instruction": random.choice(self.instruction_prompt),
                    "input": "** " + text + " **"}          # 输入两侧定界符
    response_entry = {label: [] for label in self.labels}
    if (isinstance(spans, float)) or (spans is None):      # NaN/None 双守卫
        if pd.isnull(spans):
            spans = []
    for span in spans:
        span_tokens = tokens[span["token_start"]:span["token_end"]+1]
        context, skill_span = "", ""
        if span["token_start"] == 0:
            context += "** "                                # context 也带定界符
        else:
            context += tokens[span["token_start"]-1]['text'] + \
                      (" " if tokens[span["token_start"]-1]['ws'] else "")
        for i, token in enumerate(span_tokens):
            skill_span += token['text']; context += token['text']
            if token['ws']:
                if i < len(span_tokens)-1: skill_span += " "
                context += " "
        if span["token_end"] >= len(tokens) - 1:
            context += " **"
        else:
            context += tokens[span["token_end"]+1]['text'] # 左右各 1 token 上下文
        response_entry[span["label"]].append(
            {"skill_span": skill_span, "context": context})  # 双锚点!
    prompt_entry["output"] = json.dumps(response_entry, ensure_ascii=False)
```

**映射瓶颈**：**S2 抽取格式稳定性/防幻觉**。三个可复用设计：(1) **`**` 定界符包裹输入**——输入即校验场，输出中的 span 理论上必须能在 `**...**` 内找到，天然防「输出原文没有的内容」；(2) **双锚点 `skill_span + context`**——span 本体 + 左右各 1 token 的上下文，同名 span 多次出现时靠 context 消歧（回溯定位的依据，见摘录 5）；(3) **多条 instruction 随机轮换**——训练侧抗 prompt 过拟合，推理侧可固化为单一模板。另注意 `isinstance(spans, float) or spans is None` + `pd.isnull` 是处理 pandas NaN 的三重守卫（对应我们「守卫函数类型盲区：遗漏 pd.NA」的已知根因）。

**中文化伪代码**：

```python
EXTRACT_INSTRUCTIONS = [
    "你是简历/岗位信息抽取系统。从给定文本中抽取【技能】【证书】【行业】概念。"
    '严格按 JSON 输出: {"技能": [{"concept": "...", "context": "..."}], '
    '"证书": [...], "行业": [...]}; concept 必须是原文连续片段, context 为其左右各一词。',
    "从下面文本中抽取技能与证书概念, 按 JSON 输出, 每个概念带 context 上下文。",
]   # 注意: 中文场景定界符建议换 <<< >>> 或 ###, 因 "**" 在中文简历中可能是强调符号

def build_extract_payload(text: str, labels: list) -> dict:
    # return key 集合: {ok, payload, error}
    if not isinstance(text, str):
        return {"ok": False, "payload": {}, "error": f"type error: expected str, got {type(text).__name__}"}
    payload = {"instruction": EXTRACT_INSTRUCTIONS[0],      # 推理侧固定, 训练侧轮换
               "input": "<<< " + text.strip() + " >>>"}
    return {"ok": True, "payload": payload, "error": None}
# 期望输出: {"技能": [{"concept": "熟悉ISO9001质量体系", "context": "工作内容 熟悉ISO9001质量体系 及审核"}], ...}
# 消费侧: concept 用于定界回原文, context 用于多处同名时消歧 + 交给 B2 归一器
```

- **抄什么**：定界符包裹输入、双锚点（concept+context）输出契约、instruction 轮换思想、NaN 三重守卫写法。
- **改什么**：定界符换中文安全的 `<<< >>>`；输出标签集换成我们的 技能/证书/行业；json.dumps ensure_ascii=False 保留（中文必须）。
- **扔什么**：llama-factory 数据格式外层（instruction/input/output 三元组包装）、英文 token ws 空格重建逻辑（中文无空格分词，直接用字位 offset）。

---

## 摘录 5：输出解析容错 + 回溯定位验证（Skill-LLM `combine_prediction_results.py`）

**来源**：https://raw.githubusercontent.com/herandy/Skill-LLM/master/src/postprocessing/combine_prediction_results.py ｜ **许可证**：**无许可证：仅作模式参考，禁止逐字复制到我们的代码**

**关键代码**（`find_errors_eval` + `find_best_match`，约第 70-135 行，压缩摘录）：

```python
def find_errors_eval(self, input_list):
    try:
        eval(input_list)
        return False
    except SyntaxError:
        return True          # 解析失败的预测剥离 + 单独落盘 error_data.csv 审计

def find_best_match(self, sentence, subphrase, subphrase_with_context):
    try:
        pattern = re.compile(r'\b' + re.escape(subphrase) + r'\b', re.IGNORECASE)
        matches = [(m.start(), m.end()) for m in re.finditer(pattern, sentence)]
        assert len(matches) > 0
    except AssertionError:   # 词边界失配 → 降级为裸子串匹配
        pattern = re.compile(re.escape(subphrase), re.IGNORECASE)
        matches = [(m.start(), m.end()) for m in re.finditer(pattern, sentence)]
    if not matches:
        return None, None, None
    best_match, best_score, best_start, best_end = None, -1, 0, 0
    for start, end in matches:                    # 同名 span 多次出现
        context_start = max(0, start - (len(subphrase_with_context) - len(subphrase)))
        context_end = min(len(sentence), end + (len(subphrase_with_context) - len(subphrase)))
        context = sentence[context_start:context_end]
        score = fuzz.ratio(context, subphrase_with_context)  # 用 context 模糊打分选位置
        if score > best_score:
            best_match, best_score, best_start, best_end = context, score, start, end
    return best_match, best_start, best_end

# 调用侧: 定位失败 / char_span 对齐失败均不致命
best_match, best_start, best_end = self.find_best_match(clean_text, skill_span, context)
if best_match is not None:
    span = clean_doc.char_span(best_start, best_end)
    if span is not None:
        skill_spans.append({'start': best_start, 'end': best_end-1, 'label': skill_type,
                            'token_start': span[0].i, 'token_end': span[-1].i})
    else:
        skill_spans.append({'start': best_start, 'end': best_end-1, 'label': skill_type})
```

**映射瓶颈**：**S2 round-trip 验证闭环**。这是摘录 4 输出契约的消费端，二者合成完整防幻觉回路：(1) 模型输出先过**语法体检**，失败样本单独落盘可审计（对应我们「err=None 全空=假 0%」根因——解析失败必须显式计数，不许静默吞）；(2) concept 回原文定位用**两级降级**（词边界 regex → 裸子串）；(3) 同名多处出现用 **context 模糊打分选位**；(4) 每级失败都有 None 分支且不致命。对我们：LLM 抽出的 concept 若在原文定位失败 = 高概率幻觉 → 丢弃并计数，这就是 S2 要的「输出必须可回溯到输入」硬校验。

**中文化伪代码**：

```python
def parse_and_locate(raw_output: str, source_text: str) -> dict:
    # return key 集合: {ok, items, dropped, error} (4 条路径一致)
    if not isinstance(raw_output, str) or not isinstance(source_text, str):
        return {"ok": False, "items": [], "dropped": 0,
                "error": f"type error: expected str, got {type(raw_output).__name__}/{type(source_text).__name__}"}
    try:
        parsed = json.loads(strip_code_fence(raw_output))
    except json.JSONDecodeError as e:
        log_audit(raw_output)                     # 坏输出落盘审计, 不静默吞
        return {"ok": False, "items": [], "dropped": 0, "error": f"json decode failed: {e}"}
    items, dropped = [], 0
    for ent in flatten_entities(parsed):
        loc = locate_cn(source_text, ent["concept"])          # 两级降级: 精确子串 → 归一化子串
        if loc is None and ent.get("context"):
            loc = locate_by_context_fuzzy(source_text, ent["concept"], ent["context"])  # 消歧选位
        if loc is None:
            dropped += 1                                      # 定位失败 = 疑似幻觉, 丢弃+计数
            continue
        items.append({"idx": len(items), "concept": ent["concept"],
                      "standard_label": None,                  # 留给 B2 归一器填
                      "candidates": [], "start": loc[0], "end": loc[1]})
    return {"ok": True, "items": items, "dropped": dropped, "error": None}
```

- **抄什么**：语法体检+失败样本落盘审计、两级降级定位、context 模糊选位、定位失败即丢弃并计数（防幻觉硬门）。
- **改什么**：`\b` 词边界对中文无效（中文无词边界字符），第一级改为直接子串+全半角归一化；fuzz.ratio 换中文适用的相似度；`eval()` 解析 JSON 绝不能学（代码注入），必须 json.loads。
- **扔什么**：`eval()` 用法（安全漏洞）、spaCy WhitespaceTokenizer（中文不适用）、pandas 逐行 apply 的低效结构。

---

## 摘录 6（附带）：token offset 闭区间基建（Skill-LLM `convert_iob_tags_to_offset_tags.py`）

**来源**：https://raw.githubusercontent.com/herandy/Skill-LLM/master/src/preprocessing/convert_iob_tags_to_offset_tags.py ｜ **许可证**：**无许可证：仅作模式参考，禁止逐字复制到我们的代码**

**关键代码**（`convert_iob_tags_to_jsonl()` 核心，约第 60-95 行）：

```python
doc = Doc(self.nlp.vocab, words=tokens)
json_tokens = doc.to_json()['tokens']
for i, (word, token) in enumerate(zip(tokens, json_tokens)):
    token['ws'] = i < len(tokens) - 1      # 最后一个 token 无尾随空格
    token['text'] = word
    token['end'] = token['end'] - 1        # 全库统一为闭区间 [start, end]
biluo_tags = {label: iob_to_biluo(t) for label, t in tags.items()}
try:
    spans = list(itertools.chain.from_iterable(
        [biluo_tags_to_spans(doc, t) for t in biluo_tags.values()]))
    json_spans = [{'start': s.start_char, 'end': s.end_char-1, 'label': s.label_,
                   'token_start': s.start, 'token_end': s.end-1} for s in spans]
except IndexError:
    json_spans = []                        # tokenization 失配不崩溃, 降级为空
```

**映射瓶颈**：**S2 支撑基建**。两条纪律：(1) **offset 语义全链路统一为闭区间**（`end-1`），token_start/token_end 与 char start/end 成对携带——我们 items 若加 span 字段应照此一次性定死，防止上下游 end 开闭区间漂移（对应「跨 Agent 字段契约盲区」）；(2) 标注失配 `except IndexError → 空列表` 的降级而非崩溃。

- **抄什么**：闭区间统一约定、char/token 双坐标成对携带、失配降级。
- **改什么**：中文按字符切分，无需 spaCy Doc 重建空格。
- **扔什么**：BILUO/IOB 转换链（我们不做序列标注微调则用不到）。

---

## 总览：三瓶颈 → 资产映射

| 瓶颈/步骤 | 来源 | 直接复用资产 | 许可 |
|-----------|------|-------------|------|
| **B2** 间接映射（ISO9001→质量工程） | SkillNer matcher_class + general_params | 多级 matcher 管线（高/低置信 + token 抢占）；SKILL_DB 五字段 schema（`high/low_surface_forms` 即间接词槽位）；冗余短语停用表 | MIT，可抄可改 |
| **S2** 格式稳定/防幻觉 | Skill-LLM prepare_data + combine_prediction_results | 定界符包裹输入；concept+context 双锚点输出契约；语法体检+落盘审计；两级降级回溯定位+失败即弃 | **无许可证，仅模式参考** |
| **S8** 抽取后扩展/冲突消解 | SkillNer utils.process_n_gram | 0/1 矩阵→共现聚类→span 冲突→择优骨架；「长匹配顶替须 ≥0.5 阈值」；token 位置加权 | MIT，可抄可改 |

**已知根因对照**（与我们 MEMORY.md 的衔接）：SkillNer `import 即落盘` = 「新增副作用破坏既有不变量」反面教材；原码 `len_` 变量遮蔽 bug = 审查盲区活样本；`pd.isnull` 三重守卫 = 「守卫函数类型盲区」的正面写法；Skill-LLM `eval()` 解析 = 禁止照搬点。所有伪代码已按我们契约对齐（对称顶层 key、`isinstance` 入口守卫、items 字段结构、单点常量定义）。
