"""验证"第二轮 embedding argmax"能否把第一轮的精细/方差词路由回 GT 概括标签。

背景：
- 新框架：第一轮 LLM 抽精细标签（词汇方差，如"逆境反弹"/"失败中学习"/"韧性"）
  → 第二轮对全标签集做 embedding argmax 归入固定概括标签。
- 本脚本验证 argmax 命中率：对每个 GT 概括标签构造一批"第一轮可能产出的近义词"，
  看 argmax 是否路由回正确 GT。

只读 label_corpus + embedding 模型，不改任何文件。

[ALLOWED-OPS: Read, Bash(python)]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from utils.label_embedding import encode_labels, _cosine_batch, load_label_corpus  # noqa: E402


# ── 测试集：每个 GT 概括标签 → 一批"第一轮 LLM 可能产出的精细/方差词" ──
# 这些词是 LLM 抽取时常见的同义/具体化表达，不在标签库里。
# 覆盖 GT 中全部 T2/T3 概括标签 + 一批易混淆近义场景。
#
# 字段：gt = 标签库里的概括标签名；queries = 第一轮可能产出的方差词列表；
#       tier = T2/T3。
TEST_CASES = [
    # ── T3 发展潜力（9 个，软技能，BGE 死穴区）──
    {"gt": "成长型思维", "tier": "T3", "queries": [
        "逆境反弹", "失败中学习", "韧性", "持续学习", "拥抱变化", "从挫折中恢复",
        "成长心态", "学习意愿强", "反思改进", "视挑战为机会"]},
    {"gt": "领导力潜质", "tier": "T3", "queries": [
        "非职权影响力", "带团队潜力", "自然承担leader角色", "为下属争取资源",
        "关键时刻能兜底", "激发团队", "隐性领导", "带动他人", "决策力", "管理潜质"]},
    {"gt": "抗压韧性", "tier": "T3", "queries": [
        "高压下稳定", "情绪稳定", "压力管理", "心理韧性", "关键时刻不掉链子",
        "困境中坚持", "应对危机", "紧张环境胜任"]},
    {"gt": "自驱力", "tier": "T3", "queries": [
        "主动性", "自我驱动", "主动承担责任", "无需督促", "内驱力", "自我激励",
        "自发学习", "进取心"]},
    {"gt": "战略思维", "tier": "T3", "queries": [
        "全局观", "长远规划", "战略视野", "顶层设计", "前瞻性思考", "商业洞察"]},
    {"gt": "创新能力", "tier": "T3", "queries": [
        "创新意识", "技术视野开阔", "前沿探索", "引入新技术", "创造性解决问题",
        "突破常规", "技术前瞻"]},

    # ── T2 行为能力（13 个）──
    {"gt": "跨部门协调", "tier": "T2", "queries": [
        "跨团队沟通", "部门协作", "横向协调", "推动跨部门协作", "沟通顺畅",
        "协作态度好", "打破部门墙"]},
    {"gt": "团队管理", "tier": "T2", "queries": [
        "基层管理能力", "带队", "团队建设", "人员管理", "管理下属", "团队leader",
        "组织团队"]},
    {"gt": "质量导向", "tier": "T2", "queries": [
        "质量意识强", "分内工作尽责", "追求卓越", "高标准", "严谨细致", "质量把控"]},
    {"gt": "沟通表达", "tier": "T2", "queries": [
        "口头表达清晰", "沟通直接高效", "表达流畅", "汇报清晰", "语言组织能力",
        "说服力"]},
    {"gt": "执行推进", "tier": "T2", "queries": [
        "非常靠谱", "分内工作尽责到位", "态度端正", "落地执行", "推进落地",
        "说到做到", "执行力强",
        # 泛化测试新词（不在已知漏路由里）
        "推进项目落地", "确保任务按时完成", "执行闭环"]},
    {"gt": "学习敏捷性", "tier": "T2", "queries": [
        "主动学习前沿", "新技术快速上手", "学习能力强", "快速吸收新知识",
        "技术迭代跟进", "学以致用"]},
    {"gt": "资源整合", "tier": "T2", "queries": [
        "布置任务清晰", "有主见能推动决策", "协调资源", "调配资源", "整合多方",
        "资源调度"]},
    {"gt": "变革推动", "tier": "T2", "queries": [
        "推动决策", "有主见", "主导变革", "推动改革", "打破现状", "推动落地变革"]},

    # ── T1 硬技能（取 GT 中出现的几个做对照，硬技能 BGE 应该表现好）──
    {"gt": "嵌入式开发", "tier": "T1", "queries": [
        "边缘计算网关", "MCU开发", "STM32", "固件开发", "底层驱动", "RTOS",
        "C++嵌入式", "硬件交互"]},
    {"gt": "项目管理", "tier": "T1", "queries": [
        "PMP", "Scrum管理", "进度控制", "项目交付", "敏捷迭代管理", "项目协调",
        "PMBOK"]},
    {"gt": "法务审计", "tier": "T1", "queries": [
        "合规审计", "内控体系", "风险矩阵", "COSO", "法务合规", "审计软件",
        "合规管理"]},
]


# ── C 方案：重写冲突标签的 definition+keywords 提高正交性 ──
# 原则：每个共享词只归一个标签；给被抢票的标签补独有词。
# 注意：在已知测试集上调参 = 过拟合，结果代表 C 的上限，不保证泛化。
OVERRIDES = {
    # T3：解决 韧性/逆境/恢复 三组重叠
    "成长型思维": {
        "definition": "相信能力可通过努力持续提升、面对挫折保持学习姿态、主动寻求挑战并从反馈中迭代成长的发展心态",
        "keywords": ["成长型思维", "持续学习", "拥抱挑战", "反思", "自我迭代",
                     "学习姿态", "能力提升", "求知欲", "视挑战为机会", "从反馈中成长"],
    },
    "抗压韧性": {
        "definition": "在高压力、高不确定性环境中保持情绪稳定、持续产出并从疲惫中恢复斗志的心理韧性",
        "keywords": ["抗压", "韧性", "情绪稳定", "恢复力", "高压", "压力",
                     "坚持", "关键时刻兜底", "不掉链子", "心理稳定", "逆境坚持"],
    },
    "领导力潜质": {
        "definition": "未经正式领导岗位历练即展现出愿景构建、团队激励、凝聚人心并自然承担leader角色的潜在领导品质",
        "keywords": ["领导潜质", "愿景", "激励团队", "带队", "领袖气质", "凝聚力",
                     "担当", "非职权影响", "愿景构建", "承担leader角色", "凝聚人心"],
    },
    "影响力构建": {
        "definition": "通过专业输出、观点传播和人际网络逐步建立个人专业影响力的潜在能力",
        "keywords": ["专业输出", "观点传播", "人际网络", "个人品牌",
                     "知识沉淀", "行业发声", "话语权", "个人影响力构建"],
    },
    "自驱力": {
        "definition": "不依赖外部压力即可设定目标、持续推进、自我监督与激励、主动承担责任的内生动力",
        "keywords": ["自驱", "内生动力", "目标设定", "自我监督", "自我激励",
                     "无需督促", "主动性", "主动承担", "进取心"],
    },
    # T2：解决 推进/推动、到位/可靠、沟通 三组重叠
    "执行推进": {
        "definition": "以行动和结果驱动、将计划转化为交付、克服障碍按时达成的执行行为（纯动作，不含态度/尽责）",
        "keywords": ["行动", "结果驱动", "落地", "按时交付", "克服障碍", "达成目标", "坚持推进"],
    },
    "质量导向": {
        "definition": "以零缺陷为目标、遵循规范与过程控制、保障交付质量的行为倾向",
        "keywords": ["质量", "零缺陷", "合规", "规范", "过程控制", "交付质量", "质量保障"],
    },
    "变革推动": {
        "definition": "在组织变革中识别阻力、设计过渡方案、引导团队适应新流程并持续推进变革的行为能力",
        "keywords": ["变革", "改革", "新流程", "过渡方案", "引导适应",
                     "推动变革", "打破现状", "转型", "组织变革",
                     "有主见能推动决策", "主导变革"],
    },
    "跨部门协调": {
        "definition": "在多部门/多团队协作场景中主动消除信息壁垒、推动共识达成、横向拉通协作的行为能力",
        "keywords": ["跨部门", "横向协调", "信息壁垒", "部门墙", "协作", "共识", "沟通"],
    },
    "沟通表达": {
        "definition": "清晰准确传递信息、有效倾听理解对方、适配不同受众的表达风格的行为能力",
        "keywords": ["沟通", "表达", "倾听", "汇报", "演讲",
                     "书面表达", "清晰传递", "受众适配"],
    },
    "学习敏捷性": {
        "definition": "在变化环境中快速学习新知识/新技能、迁移已有经验、灵活应用到新场景的行为能力",
        "keywords": ["学习", "敏捷", "迁移", "适应", "快速上手",
                     "经验复用", "新知识", "学以致用", "技术迭代"],
    },
    "资源整合": {
        "definition": "识别可用资源、跨渠道整合、优化配置以最大化产出效益的行为能力",
        "keywords": ["资源整合", "配置优化", "调度", "跨渠道",
                     "效益", "盘活资源", "调配",
                     "布置任务清晰", "整合多方", "资源调度"],
    },
}


# ── D 方案：T3 合并 韧性/成长 一对标签（argmax 永远分不开）──
MERGE_MAP_T3 = {
    "成长型思维": "韧性与成长心态",
    "抗压韧性": "韧性与成长心态",
}
MERGE_DEF_T3 = {
    "韧性与成长心态": {
        "definition": "面对挫折与高压时保持学习姿态、从逆境中反弹、相信能力可经努力持续提升的韧性与成长心态",
        "keywords": ["韧性", "逆境反弹", "持续学习", "拥抱挑战", "反思",
                     "自我迭代", "抗压", "情绪稳定", "恢复力", "高压稳定",
                     "从挫折中恢复", "学习姿态", "能力提升"],
    },
}


# ── E 方案：层内正交重排版（T2=14 含尽责性 / T3=7 含合并后韧性与成长心态）──
# 原则：每个标签唯一 Factor 归属；冲突共享词（推进/推动/沟通/影响力/主动性）从冲突对
# 双方删除或独占给一方；态度词（靠谱/尽责）整体移出 T2 执行推进归 T2 尽责性。
# 跨层重叠（执行推进↔尽责性、战略思维↔战略眼光）按用户指示不处理（独立提取）。
NEW_LABELS_T2 = [
    {"name": "跨部门协调", "tier": "T2_行为能力",
     "definition": "打破部门壁垒、横向拉通资源与信息、推动多方达成共识的协作能力",
     "keywords": ["跨部门", "横向协调", "信息壁垒", "部门墙", "协作", "共识", "沟通"]},
    {"name": "团队管理", "tier": "T2_行为能力",
     "definition": "带领团队、激励成员、授权分工、处理冲突以达成目标的管理行为",
     "keywords": ["团队管理", "激励", "授权", "冲突处理", "目标驱动", "带队"]},
    {"name": "问题解决", "tier": "T2_行为能力",
     "definition": "分析复杂问题、定位根因、设计方案并验证决策的思维能力",
     "keywords": ["问题解决", "根因分析", "方案设计", "决策", "分析推理", "验证"]},
    {"name": "学习敏捷性", "tier": "T2_行为能力",
     "definition": "快速学习新知识、迁移已有经验、适应技术迭代的学习能力",
     "keywords": ["学习敏捷", "快速上手", "经验复用", "迁移应用", "技术迭代"]},
    {"name": "沟通表达", "tier": "T2_行为能力",
     "definition": "准确表达、有效倾听、根据受众调整信息传递的沟通能力",
     "keywords": ["沟通", "表达", "倾听", "汇报", "演讲", "书面表达", "受众适配"]},
    {"name": "客户导向", "tier": "T2_行为能力",
     "definition": "理解客户需求、主动服务、持续优化交付以满足客户的行为倾向",
     "keywords": ["客户导向", "需求理解", "服务意识", "客户满意度", "交付优化"]},
    {"name": "执行推进", "tier": "T2_行为能力",
     "definition": "以行动和结果驱动、将计划转化为交付、克服障碍按时达成的执行行为",
     "keywords": ["行动", "结果驱动", "落地", "按时交付", "克服障碍", "达成目标", "坚持推进"]},
    {"name": "创新思维", "tier": "T2_行为能力",
     "definition": "突破常规、提出新方案、创造性解决问题的思维能力",
     "keywords": ["创新", "创意", "突破常规", "新方案", "试错", "创造性解决"]},
    {"name": "风险意识", "tier": "T2_行为能力",
     "definition": "识别潜在风险、预警预案、前瞻防控以降低损失的判断能力",
     "keywords": ["风险识别", "预警", "预案", "止损", "风险评估", "前瞻防控"]},
    {"name": "资源整合", "tier": "T2_行为能力",
     "definition": "盘活多方资源、优化配置调度以支撑目标达成的能力",
     "keywords": ["资源整合", "配置优化", "调度", "盘活资源", "整合多方", "资源调配"]},
    {"name": "变革推动", "tier": "T2_行为能力",
     "definition": "推动组织或流程变革、打破现状、引入新机制以实现转型的能力",
     "keywords": ["变革", "转型", "改革", "打破现状", "新流程", "组织变革"]},
    {"name": "战略思维", "tier": "T2_行为能力",
     "definition": "从全局视角识别杠杆点、把握方向与长期视角的思维能力",
     "keywords": ["战略思维", "全局观", "杠杆点", "方向", "长期视角", "战略规划"]},
    {"name": "质量导向", "tier": "T2_行为能力",
     "definition": "以零缺陷为目标、遵循规范与过程控制、保障交付质量的行为倾向",
     "keywords": ["质量", "零缺陷", "合规", "规范", "过程控制", "交付质量", "质量保障"]},
    {"name": "尽责性", "tier": "T2_行为能力",
     "definition": "个人特质层面靠谱自律、信守承诺、对细节与高标准保持关注的品质",
     "keywords": ["尽责", "靠谱", "承诺", "自律", "条理", "细节关注", "承诺兑现", "高标准"]},
]
NEW_LABELS_T3 = [
    {"name": "领导力潜质", "tier": "T3_发展潜力",
     "definition": "构建愿景、激励他人、凝聚人心、具备带队与决策担当潜力的领导特质",
     "keywords": ["愿景构建", "激励他人", "凝聚人心", "承担leader", "承担leader角色", "带队潜质", "决策担当", "团队决策"]},
    {"name": "影响力构建", "tier": "T3_发展潜力",
     "definition": "通过专业输出与观点传播、建立个人品牌与话语权的影响力潜力",
     "keywords": ["专业输出", "观点传播", "人际网络", "个人品牌", "话语权", "行业发声"]},
    {"name": "自驱力", "tier": "T3_发展潜力",
     "definition": "内生动力驱动、自主设定目标、无需外部督促持续进取的特质",
     "keywords": ["内生动力", "目标设定", "自我监督", "进取心", "自觉", "无需督促"]},
    {"name": "开放性", "tier": "T3_发展潜力",
     "definition": "保持好奇、乐于探索、接纳多元视角与想象的开放心态",
     "keywords": ["开放", "好奇心", "探索", "多元视角", "想象力", "审美"]},
    {"name": "战略眼光", "tier": "T3_发展潜力",
     "definition": "前瞻趋势、洞察技术演进、形成长远判断的战略潜力",
     "keywords": ["战略眼光", "趋势判断", "前瞻", "技术视野", "长远洞察"]},
    {"name": "跨界整合潜力", "tier": "T3_发展潜力",
     "definition": "跨越多领域、发现关联、迁移知识以实现跨域整合的潜力",
     "keywords": ["跨界", "多领域", "关联发现", "知识迁移", "跨域整合"]},
    {"name": "韧性与成长心态", "tier": "T3_发展潜力",
     "definition": "面对挫折与高压时保持学习姿态、逆境反弹、持续自我迭代的潜力",
     "keywords": ["韧性", "逆境反弹", "持续学习", "拥抱挑战", "抗压", "情绪稳定", "恢复力", "从挫折中恢复"]},
]

# E 方案下旧 TEST_CASES 的 GT 映射（成长型思维/抗压韧性 → 韧性与成长心态）
E_GT_MAP = {
    "成长型思维": "韧性与成长心态",
    "抗压韧性": "韧性与成长心态",
}

# E 方案新增/合并标签的补充 queries（旧 TEST_CASES 未覆盖）
# A2：T2 用 D 方案 13 标签（无尽责性），态度词漂到执行推进/质量导向（已在原 TEST_CASES）
EXTRA_TEST_CASES = [
    {"gt": "开放性", "tier": "T3", "queries": [
        "好奇心强", "乐于探索新事物", "接纳不同观点", "思维活跃", "想象力丰富",
        "审美能力"]},
    {"gt": "战略眼光", "tier": "T3", "queries": [
        "前瞻性思考", "技术视野开阔", "长远规划", "趋势判断准", "商业洞察",
        "战略视野"]},
    {"gt": "跨界整合潜力", "tier": "T3", "queries": [
        "跨领域整合", "知识迁移能力强", "关联发现", "多领域融合", "跨域思维"]},
    {"gt": "影响力构建", "tier": "T3", "queries": [
        "个人品牌", "行业发声", "话语权", "观点传播广", "专业输出有影响力",
        "人际网络广"]},
    {"gt": "韧性与成长心态", "tier": "T3", "queries": [
        "逆境反弹", "失败中学习", "韧性", "持续学习", "拥抱变化", "从挫折中恢复",
        "成长心态", "学习意愿强", "反思改进", "视挑战为机会",
        "高压下稳定", "情绪稳定", "压力管理", "心理韧性", "关键时刻不掉链子",
        "困境中坚持", "应对危机", "紧张环境胜任"]},
]


def _tier_items(corpus, tier):
    return [it for it in corpus if it["tier"] == tier]


def _apply_merge(items, merge_map, merge_def):
    """按 merge_map 合并标签，合并后的定义取自 merge_def。"""
    merged = {}
    out = []
    for it in items:
        name = it["name"]
        target = merge_map.get(name)
        if target is None:
            out.append(it)
            continue
        if target not in merged:
            merged[target] = {"name": target,
                             "definition": merge_def[target]["definition"],
                             "keywords": merge_def[target]["keywords"],
                             "tier": it["tier"]}
            out.append(merged[target])
    return out


def _build_label_matrix(items, encode_fn=None, use_override=True, use_merge_t3=False):
    """返回 (names, matrix)。text 用 name+definition+keywords 拼接（信息丰富版）。

    use_merge_t3=True 时先合并 T3 韧性/成长对（D 方案）。
    use_override=True 时应用 OVERRIDES（C 方案正交化）。
    """
    if use_merge_t3:
        items = _apply_merge(items, MERGE_MAP_T3, MERGE_DEF_T3)
    texts = []
    names = []
    for it in items:
        name = it["name"]
        if use_override and name in OVERRIDES:
            ov = OVERRIDES[name]
            definition = ov["definition"]
            keywords = ov["keywords"]
        else:
            definition = it.get("definition", "")
            keywords = it.get("keywords", [])
        kw = "、".join(keywords)
        text = f"{name}。{definition}。关键词：{kw}"
        texts.append(text)
        names.append(name)
    mat = encode_labels(texts, encode_fn=encode_fn)
    return names, mat


def _cosine_batch_batch(q_vecs, matrix):
    """(Q, dim) vs (N, dim) → (Q, N)。复用 _cosine_batch 逐行。"""
    rows = []
    for i in range(q_vecs.shape[0]):
        rows.append(_cosine_batch(q_vecs[i], matrix))
    return np.array(rows)


def run(encode_fn=None, use_override=True, use_merge_t3=False,
        label="C 方案（正交化）"):
    corpus = load_label_corpus()
    tiers = {"T1": _tier_items(corpus, "T1_专业能力"),
             "T2": _tier_items(corpus, "T2_行为能力"),
             "T3": _tier_items(corpus, "T3_发展潜力")}
    matrices = {t: _build_label_matrix(its, encode_fn, use_override=use_override,
                                       use_merge_t3=(t == "T3" and use_merge_t3))
                for t, its in tiers.items()}

    print("=" * 80)
    print(f"argmax 路由验证（{label}）")
    print(f"标签集规模：T1={len(tiers['T1'])}  T2={len(tiers['T2'])}  T3={len(tiers['T3'])}"
          + (f" → 合并后 {len(matrices['T3'][0])}" if use_merge_t3 else ""))
    print(f"文本构造：name + definition + keywords"
          + (" + OVERRIDES" if use_override else " 原版")
          + (" + T3 MERGE" if use_merge_t3 else ""))
    print("=" * 80)

    # D 方案：合并模式下，把同 GT 的 queries 聚合，避免双计
    cases = TEST_CASES
    if use_merge_t3:
        merged_cases = {}
        for case in TEST_CASES:
            tier = case["tier"]
            gt = case["gt"]
            if tier == "T3" and gt in MERGE_MAP_T3:
                gt = MERGE_MAP_T3[gt]
            key = (tier, gt)
            if key not in merged_cases:
                merged_cases[key] = {"tier": tier, "gt": gt, "queries": []}
            merged_cases[key]["queries"].extend(case["queries"])
        cases = list(merged_cases.values())

    total_q = 0
    total_hit = 0
    per_case = []
    for case in cases:
        tier = case["tier"]
        gt = case["gt"]
        queries = case["queries"]
        names, mat = matrices[tier]
        if gt not in names:
            print(f"\n[WARN] GT '{gt}' 不在 {tier} 标签集，跳过")
            continue
        gt_idx = names.index(gt)

        q_vecs = encode_labels(queries, encode_fn=encode_fn)
        if q_vecs.size == 0:
            continue
        sims = _cosine_batch_batch(q_vecs, mat)  # (Q, N)
        hits = 0
        detail = []
        for i, q in enumerate(queries):
            top_idx = int(np.argmax(sims[i]))
            top_name = names[top_idx]
            top_sim = float(sims[i][top_idx])
            gt_sim = float(sims[i][gt_idx])
            hit = (top_idx == gt_idx)
            if hit:
                hits += 1
            detail.append((q, top_name, round(top_sim, 3), round(gt_sim, 3), hit))
        total_q += len(queries)
        total_hit += hits
        rate = hits / len(queries)
        per_case.append((tier, gt, hits, len(queries), rate, detail))

    print(f"\n{'tier':<4} {'GT 概括标签':<14} {'命中':<10} {'命中率':<8}  漏路由明细")
    print("-" * 80)
    for tier, gt, hits, n, rate, detail in per_case:
        miss = [(q, top) for (q, top, _, _, hit) in detail if not hit]
        miss_str = "; ".join(f"{q}→{top}" for q, top in miss) if miss else "—"
        flag = "  " if rate == 1.0 else " !"
        print(f"{tier:<4} {gt:<14} {hits}/{n:<8} {rate*100:5.1f}%  {miss_str}{flag}")

    print("\n" + "=" * 80)
    print(f"总体 argmax 命中率：{total_hit}/{total_q} = {total_hit/total_q*100:.1f}%")
    for t in ["T1", "T2", "T3"]:
        cases_t = [c for c in per_case if c[0] == t]
        if cases_t:
            h = sum(c[2] for c in cases_t)
            n = sum(c[3] for c in cases_t)
            print(f"  {t}: {h}/{n} = {h/n*100:.1f}%")
    print("=" * 80)
    print("\n判断标准（新框架可行性）：")
    print("  argmax 命中率 >= 80% -> 方案成立，第二轮纯 embedding 可行")
    print("  60-80% -> 边界，需加 LLM 兜底（argmax score 低者过 Agent2）")
    print("  < 60% -> argmax 不可行，第二轮必须换 LLM")


def _build_e_matrix(items, encode_fn=None):
    """E 方案：直接用 NEW_LABELS 的 definition+keywords 构造矩阵（无 OVERRIDES/MERGE）。"""
    texts = []
    names = []
    for it in items:
        name = it["name"]
        definition = it.get("definition", "")
        keywords = it.get("keywords", [])
        kw = "、".join(keywords)
        text = f"{name}。{definition}。关键词：{kw}"
        texts.append(text)
        names.append(name)
    mat = encode_labels(texts, encode_fn=encode_fn)
    return names, mat


def run_e(encode_fn=None, label="E 方案 A2（T2=D方案13 / T3=E重排7）"):
    """A2：T2 用 D 方案标签集（corpus + OVERRIDES，13 标签，态度词内部抢票可接受），
    T3 用 NEW_LABELS_T3（7 标签，合并韧性与成长心态）。"""
    corpus = load_label_corpus()
    # T2 = D 方案：corpus T2 + OVERRIDES（与 run(use_override=True) 同源）
    t2_corpus = [it for it in corpus if it["tier"] == "T2_行为能力"]
    # T1 维持原 corpus
    tiers = {"T1": [it for it in corpus if it["tier"] == "T1_专业能力"],
             "T2": t2_corpus,
             "T3": NEW_LABELS_T3}
    matrices = {}
    for t, its in tiers.items():
        if t == "T2":
            # D 方案：corpus item + 应用 OVERRIDES（与 _build_label_matrix(use_override=True) 同逻辑）
            texts, names = [], []
            for it in its:
                name = it["name"]
                if name in OVERRIDES:
                    ov = OVERRIDES[name]
                    definition, keywords = ov["definition"], ov["keywords"]
                else:
                    definition, keywords = it.get("definition", ""), it.get("keywords", [])
                kw = "、".join(keywords)
                texts.append(f"{name}。{definition}。关键词：{kw}")
                names.append(name)
            from utils.label_embedding import encode_labels as _enc
            matrices[t] = (names, _enc(texts, encode_fn=encode_fn))
        else:
            matrices[t] = _build_e_matrix(its, encode_fn)

    print("=" * 80)
    print(f"argmax 路由验证（{label}）")
    print(f"标签集规模：T1={len(tiers['T1'])}  T2={len(tiers['T2'])}  T3={len(tiers['T3'])}")
    print("文本构造：T2=corpus+OVERRIDES(D方案) / T3=NEW_LABELS(E重排)")
    print("=" * 80)

    # 合并 TEST_CASES（经 E_GT_MAP 映射）+ EXTRA_TEST_CASES，同 GT 聚合
    merged_cases = {}
    for case in TEST_CASES + EXTRA_TEST_CASES:
        tier = case["tier"]
        gt = case["gt"]
        if tier == "T3" and gt in E_GT_MAP:
            gt = E_GT_MAP[gt]
        key = (tier, gt)
        if key not in merged_cases:
            merged_cases[key] = {"tier": tier, "gt": gt, "queries": []}
        merged_cases[key]["queries"].extend(case["queries"])
    cases = list(merged_cases.values())

    total_q = 0
    total_hit = 0
    per_case = []
    for case in cases:
        tier = case["tier"]
        gt = case["gt"]
        queries = case["queries"]
        names, mat = matrices[tier]
        if gt not in names:
            print(f"\n[WARN] GT '{gt}' 不在 {tier} 标签集，跳过")
            continue
        gt_idx = names.index(gt)

        q_vecs = encode_labels(queries, encode_fn=encode_fn)
        if q_vecs.size == 0:
            continue
        sims = _cosine_batch_batch(q_vecs, mat)  # (Q, N)
        hits = 0
        detail = []
        for i, q in enumerate(queries):
            top_idx = int(np.argmax(sims[i]))
            top_name = names[top_idx]
            top_sim = float(sims[i][top_idx])
            gt_sim = float(sims[i][gt_idx])
            hit = (top_idx == gt_idx)
            if hit:
                hits += 1
            detail.append((q, top_name, round(top_sim, 3), round(gt_sim, 3), hit))
        total_q += len(queries)
        total_hit += hits
        rate = hits / len(queries)
        per_case.append((tier, gt, hits, len(queries), rate, detail))

    print(f"\n{'tier':<4} {'GT 概括标签':<14} {'命中':<10} {'命中率':<8}  漏路由明细")
    print("-" * 80)
    for tier, gt, hits, n, rate, detail in per_case:
        miss = [(q, top) for (q, top, _, _, hit) in detail if not hit]
        miss_str = "; ".join(f"{q}→{top}" for q, top in miss) if miss else "—"
        flag = "  " if rate == 1.0 else " !"
        print(f"{tier:<4} {gt:<14} {hits}/{n:<8} {rate*100:5.1f}%  {miss_str}{flag}")

    print("\n" + "=" * 80)
    print(f"总体 argmax 命中率：{total_hit}/{total_q} = {total_hit/total_q*100:.1f}%")
    for t in ["T1", "T2", "T3"]:
        cases_t = [c for c in per_case if c[0] == t]
        if cases_t:
            h = sum(c[2] for c in cases_t)
            n = sum(c[3] for c in cases_t)
            print(f"  {t}: {h}/{n} = {h/n*100:.1f}%")
    print("=" * 80)


if __name__ == "__main__":
    import os
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    print("\n\n########## BASELINE（原 keywords）##########\n")
    run(use_override=False, use_merge_t3=False, label="baseline 原版")
    print("\n\n########## C 方案（正交化 keywords）##########\n")
    run(use_override=True, use_merge_t3=False, label="C 方案正交化")
    print("\n\n########## D 方案（C 正交化 + T3 合并韧性/成长）##########\n")
    run(use_override=True, use_merge_t3=True, label="D 方案 C+T3合并")
    print("\n\n########## E 方案（层内正交重排版 T2=14/T3=7）##########\n")
    run_e(label="E 方案层内正交重排")
