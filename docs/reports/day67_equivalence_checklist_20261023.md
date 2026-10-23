# 等价表核验清单（Round 3 §三，人工打勾）

> 生成：2026-10-23T13:54:11｜全量未筛选概念流 11,920 对判定（relevant_only 9142 / direct_support 1443 / equivalent 495 / state_different 517 / contradiction 323）→ 词对提议 715 条（已滤同词对）

## 核验规则（先读这里）

- **只勾你确认成立的映射：核验列填 ✓**；不成立/不确定留空或填 ✗
- **高频段（支持对数 ≥3，共 163 条）建议逐条核验**——这些直接决定排名；
- **低频段（<3，共 552 条）默认不入表**，除非你主动加 ✓（宁缺勿滥：表是运行时硬闸门，错一条污染所有岗位）
- 判定口径：equivalent=不同措辞同一能力（调度工具↔调度平台）；direct_support=下位实例（数据分析↔Pandas取数建模）；两者入表后同档计分
- 勾完保存，回复「核验完成」，我跑 `--apply` 版本化入表 v1 并重跑冒烟验证提升

## 第一部分：高频段（163 条，建议全核验）

| # | 要求侧词 | 证据侧词 | 关系 | 支持对数 | 员工数 | 涉及岗位 | 核验 |
|---|----------|----------|------|----------|--------|----------|------|
| 1 | 激励成员 | 能激发团队士气 | equivalent | 67 | 26 | JOB_B07,JOB_B08,JOB_B09,JOB_B10 | |
| 2 | 团队管理经验或潜力 | 有带团队潜力 | direct_support | 27 | 18 | JOB_B07,JOB_B10 | |
| 3 | 交付 | 负责交付管理 | direct_support | 23 | 7 | JOB_B07,JOB_B08 | |
| 4 | 主动承担 | 主动承担团队责任 | equivalent | 23 | 23 | JOB_B10 | |
| 5 | 良好的沟通协调能力与质量意识 | 质量意识强 | direct_support | 22 | 22 | JOB_B01 | |
| 6 | 以骨干身份带动团队 | 自然承担leader角色 | direct_support | 21 | 21 | JOB_B06 | |
| 7 | bi | powerbi | direct_support | 21 | 11 | JOB_B07 | |
| 8 | 执行推进可靠 | 非常靠谱 | equivalent | 20 | 19 | JOB_B08 | |
| 9 | 薪酬福利与劳动关系管理 | 薪酬体系改革 | direct_support | 19 | 15 | JOB_B08 | |
| 10 | 激励学员 | 能激发团队士气 | equivalent | 19 | 19 | JOB_B09 | |
| 11 | 与跨职能团队沟通协作 | 团队协作顺畅 | equivalent | 18 | 18 | JOB_B06 | |
| 12 | 良好的沟通表达与执行推进能力 | 口头表达清晰 | direct_support | 17 | 17 | JOB_B02 | |
| 13 | 协调多部门资源 | 负责资源协调 | equivalent | 17 | 11 | JOB_B04 | |
| 14 | 面向不同受众清晰表达与汇报 | 口头表达清晰 | equivalent | 16 | 16 | JOB_B09 | |
| 15 | 学习能力强 | 学习速度快 | equivalent | 14 | 10 | JOB_B02 | |
| 16 | 团队管理经验或潜力 | 具备基层管理能力 | direct_support | 14 | 11 | JOB_B07,JOB_B10 | |
| 17 | 团队管理与执行推进可靠 | 具备基层管理能力 | direct_support | 14 | 14 | JOB_B09 | |
| 18 | 学习敏捷性：快速学习新知识新技能 | 学习速度快 | equivalent | 13 | 13 | JOB_B06 | |
| 19 | 较强的流程梳理与交付管理能力 | 独立交付ok | direct_support | 13 | 13 | JOB_B05 | |
| 20 | 团队管理经验或潜力 | 承担过负责人角色 | direct_support | 13 | 9 | JOB_B07,JOB_B10 | |
| 21 | 学习敏捷 | 学习速度快 | direct_support | 13 | 13 | JOB_B08 | |
| 22 | 质量导向：标准合规 | 质量意识强 | equivalent | 12 | 12 | JOB_B06 | |
| 23 | 风险管理与交付验收 | 负责交付管理 | equivalent | 12 | 7 | JOB_B07 | |
| 24 | java及相关框架 | java | direct_support | 12 | 8 | JOB_B10 | |
| 25 | 良好的沟通表达与执行推进能力 | 跨部门沟通顺畅 | equivalent | 11 | 11 | JOB_B02 | |
| 26 | 主导方案设计与流程优化 | 负责方案设计 | direct_support | 11 | 9 | JOB_B04 | |
| 27 | 较强的流程梳理与交付管理能力 | 负责交付管理 | direct_support | 11 | 7 | JOB_B05 | |
| 28 | 进度控制 | 质量和进度符合预期 | equivalent | 11 | 10 | JOB_B07 | |
| 29 | 领导潜质发展通道 | 领导潜质 | equivalent | 11 | 6 | JOB_B09 | |
| 30 | 主动承担 | 主动承担责任 | equivalent | 11 | 11 | JOB_B10 | |
| 31 | 有领导潜质者优先 | 展现杰出专业能力和领导潜质 | direct_support | 10 | 5 | JOB_B06 | |
| 32 | 发挥影响力与担当 | 主动承担团队责任 | direct_support | 10 | 10 | JOB_B06 | |
| 33 | 团队管理经验或潜力 | 自然承担leader角色 | direct_support | 10 | 9 | JOB_B07,JOB_B10 | |
| 34 | 团队管理经验或潜力 | 领导力测评良好 | direct_support | 10 | 8 | JOB_B07,JOB_B10 | |
| 35 | 组建与管理研发小组：分配职责 | 布置任务清晰 | equivalent | 10 | 10 | JOB_B07 | |
| 36 | 带领项目团队：分配职责 | 布置任务清晰 | equivalent | 10 | 10 | JOB_B08 | |
| 37 | 成长型思维与领导潜质者优先 | 领导力测评良好 | direct_support | 10 | 10 | JOB_B09 | |
| 38 | 负责java后端服务与企业应用开发 | java | direct_support | 10 | 7 | JOB_B10 | |
| 39 | 嵌入式开发 | 嵌入式 | equivalent | 9 | 6 | JOB_B06 | |
| 40 | 良好的沟通表达与执行推进能力 | 沟通直接高效 | direct_support | 9 | 9 | JOB_B02 | |
| 41 | bi | bi报表 | direct_support | 9 | 5 | JOB_B07 | |
| 42 | 持续学习 | 主动学习前沿 | direct_support | 9 | 9 | JOB_B08 | |
| 43 | 演讲 | 口头表达清晰 | direct_support | 9 | 9 | JOB_B09 | |
| 44 | 与跨职能团队沟通协作 | 跨部门沟通顺畅 | equivalent | 8 | 8 | JOB_B06 | |
| 45 | 领导潜质发展通道 | 展现杰出专业能力和领导潜质 | equivalent | 8 | 5 | JOB_B06,JOB_B09 | |
| 46 | 良好的沟通表达与执行推进能力 | 质量和进度符合预期 | direct_support | 8 | 6 | JOB_B02 | |
| 47 | sql | sqlserver | direct_support | 8 | 4 | JOB_B07 | |
| 48 | 关注标准合规与可靠性 | 涉及合规审计等技术应用 | direct_support | 8 | 5 | JOB_B07 | |
| 49 | 持续学习新方法新工具并迁移到hr场景 | saphr | direct_support | 8 | 6 | JOB_B08 | |
| 50 | 沟通表达出色 | 口头表达清晰 | equivalent | 8 | 8 | JOB_B09 | |
| 51 | 有领导潜质者优先 | 自然承担leader角色 | equivalent | 7 | 7 | JOB_B06 | |
| 52 | 以骨干身份带动团队 | 角色：技术负责人 | direct_support | 7 | 7 | JOB_B06 | |
| 53 | 以骨干身份带动团队 | 承担过负责人角色 | direct_support | 7 | 7 | JOB_B06 | |
| 54 | 智慧园区 | 智慧园区平台 | direct_support | 7 | 5 | JOB_B01 | |
| 55 | 大数据平台调度工具 | airflow | direct_support | 7 | 4 | JOB_B02 | |
| 56 | 薪酬体系设计与合规审计流程 | 薪酬体系改革 | direct_support | 7 | 7 | JOB_B04 | |
| 57 | 有数字化平台项目管理与跨部门资源协调经验 | 参与人力资源数字化平台，负责资源协调 | equivalent | 7 | 4 | JOB_B04 | |
| 58 | 使用审计软件开展内控测试与整改跟踪 | 涉及审计软件等技术应用 | direct_support | 7 | 4 | JOB_B05 | |
| 59 | 可视化 | 数字孪生可视化平台 | direct_support | 7 | 5 | JOB_B07 | |
| 60 | 目标驱动 | 目标管理与okr（已完成） | direct_support | 7 | 7 | JOB_B07 | |
| 61 | iso9001 | 质量管理体系iso9001 | direct_support | 6 | 5 | JOB_B01 | |
| 62 | 良好的沟通表达与执行推进能力 | 沟通反馈正面 | direct_support | 6 | 6 | JOB_B02 | |
| 63 | 工业大数据平台开发经验者优先 | 工业大数据分析平台 | direct_support | 6 | 6 | JOB_B03 | |
| 64 | 有数字化平台项目管理与跨部门资源协调经验 | 参与人力资源数字化平台，负责方案设计 | direct_support | 6 | 4 | JOB_B04 | |
| 65 | 负责薪酬体系改革方案设计与合规审计推动 | 参与薪酬体系改革，负责方案设计，涉及岗评工具等技术应用 | direct_support | 6 | 3 | JOB_B04 | |
| 66 | 统筹人才盘点与全面预算管理项目 | 人才盘点项目 | direct_support | 6 | 3 | JOB_B04 | |
| 67 | 主导方案设计与流程优化 | 负责流程优化 | equivalent | 6 | 4 | JOB_B04 | |
| 68 | 风险管理 | 风险矩阵 | direct_support | 6 | 5 | JOB_B07,JOB_B08 | |
| 69 | 项目管理方法论 | 项目负责人 | equivalent | 6 | 6 | JOB_B08 | |
| 70 | 跨部门协调：主动沟通 | 跨部门沟通顺畅 | equivalent | 6 | 6 | JOB_B08 | |
| 71 | 持续学习新方法新工具并迁移到hr场景 | 人力资源数字化平台 | direct_support | 6 | 5 | JOB_B08 | |
| 72 | 成长型思维与领导潜质者优先 | 展现杰出专业能力和领导潜质 | direct_support | 6 | 5 | JOB_B09 | |
| 73 | 团队管理与执行推进可靠 | 关键时刻能兜底 | direct_support | 6 | 6 | JOB_B09 | |
| 74 | 带领研发小组：组建团队 | 承担过负责人角色 | equivalent | 6 | 6 | JOB_B10 | |
| 75 | 质量导向：标准合规 | 质量管理体系iso9001 | direct_support | 5 | 5 | JOB_B06 | |
| 76 | 学习敏捷性：快速学习新知识新技能 | 主动学习前沿 | equivalent | 5 | 5 | JOB_B06 | |
| 77 | 沟通表达与执行推进良好 | 跨部门沟通顺畅 | direct_support | 5 | 5 | JOB_B06 | |
| 78 | 沟通表达与执行推进良好 | 口头表达清晰 | equivalent | 5 | 5 | JOB_B06 | |
| 79 | 与跨职能团队沟通协作 | 获得跨部门一致认可 | direct_support | 5 | 3 | JOB_B06 | |
| 80 | 推动研发任务按期闭环交付 | 负责交付管理 | equivalent | 5 | 4 | JOB_B06 | |
| 81 | 工业物联网 | 工业iot管理平台 | equivalent | 5 | 3 | JOB_B01 | |
| 82 | 良好的沟通表达与执行推进能力 | 配合到位 | direct_support | 5 | 5 | JOB_B02 | |
| 83 | 输出数据分析报告 | 工业大数据分析平台 | direct_support | 5 | 4 | JOB_B02 | |
| 84 | 有erp系统 | erp系统定制开发 | direct_support | 5 | 3 | JOB_B03 | |
| 85 | 统筹人才盘点与全面预算管理项目 | 全面预算管理系统 | direct_support | 5 | 5 | JOB_B04 | |
| 86 | 统筹人才盘点与全面预算管理项目 | 参与全面预算管理系统 | direct_support | 5 | 5 | JOB_B04 | |
| 87 | 负责企业内控体系建设项目统筹与协调 | 参与企业内控体系建设，负责资源协调 | direct_support | 5 | 3 | JOB_B05 | |
| 88 | 可视化 | tableau | direct_support | 5 | 4 | JOB_B07 | |
| 89 | 进度管理 | 质量和进度符合预期 | equivalent | 5 | 4 | JOB_B07,JOB_B08 | |
| 90 | 主导业务数据分析 | 工业大数据分析平台 | direct_support | 5 | 3 | JOB_B07 | |
| 91 | 激励成员 | 团队建设与激励（已完成） | direct_support | 5 | 3 | JOB_B07,JOB_B08 | |
| 92 | 绩效管理 | 培训：绩效管理实务（已完成） | direct_support | 5 | 5 | JOB_B08 | |
| 93 | 带领项目团队：分配职责 | 角色：项目负责人 | direct_support | 5 | 4 | JOB_B08 | |
| 94 | 人力资源综合管理知识 | 人力资源主管 | direct_support | 5 | 5 | JOB_B09 | |
| 95 | 领导潜质发展通道 | 领导力测评良好 | direct_support | 4 | 4 | JOB_B06 | |
| 96 | 良好的沟通协调能力与质量意识 | 跨部门沟通顺畅 | direct_support | 4 | 4 | JOB_B01 | |
| 97 | iso9001 | 质量管理体系iso9001（已完成） | direct_support | 4 | 4 | JOB_B01 | |
| 98 | 学习能力强 | 主动学习前沿 | equivalent | 4 | 4 | JOB_B02 | |
| 99 | 负责工业大数据分析平台的开发与优化 | 参与工业大数据分析平台，负责性能优化 | direct_support | 4 | 2 | JOB_B02 | |
| 100 | java及微服务架构 | 涉及java等技术应用 | direct_support | 4 | 3 | JOB_B03 | |
| 101 | java及微服务架构 | java | direct_support | 4 | 4 | JOB_B03 | |
| 102 | 薪酬体系设计与合规审计流程 | 参与薪酬体系改革 | direct_support | 4 | 3 | JOB_B04 | |
| 103 | 主导人力资源数字化平台建设与bi分析落地 | tableau | direct_support | 4 | 3 | JOB_B04 | |
| 104 | 主导内控审计协调与流程梳理优化 | 企业内控体系建设，负责资源协调，涉及审计软件 | direct_support | 4 | 2 | JOB_B05 | |
| 105 | 数据分析完整能力链 | 工业大数据分析平台 | direct_support | 4 | 2 | JOB_B07 | |
| 106 | pmp | 项目管理pmp认证（已完成） | direct_support | 4 | 3 | JOB_B07,JOB_B08 | |
| 107 | 质量导向 | 质量管理体系iso9001 | direct_support | 4 | 4 | JOB_B07 | |
| 108 | 质量导向 | 质量和进度符合预期 | direct_support | 4 | 4 | JOB_B07 | |
| 109 | 团队管理经验或潜力 | 领导潜质 | direct_support | 4 | 2 | JOB_B07,JOB_B10 | |
| 110 | 承担项目全生命周期管理：范围界定 | 角色：项目负责人 | direct_support | 4 | 4 | JOB_B07 | |
| 111 | 目标驱动达成 | 目标管理与okr（已完成） | direct_support | 4 | 4 | JOB_B08 | |
| 112 | 沟通表达出色 | 沟通直接高效 | equivalent | 4 | 4 | JOB_B09 | |
| 113 | 团队管理与执行推进可靠 | 布置任务清晰 | direct_support | 4 | 4 | JOB_B09 | |
| 114 | 组建与管理讲师团队：分配职责 | 布置任务清晰 | equivalent | 4 | 4 | JOB_B09 | |
| 115 | 持续学习 | 培训：绩效管理实务（已完成） | direct_support | 4 | 4 | JOB_B09 | |
| 116 | 沟通表达清晰 | 口头表达清晰 | equivalent | 4 | 4 | JOB_B10 | |
| 117 | 目标设定 | 目标管理与okr（已完成） | direct_support | 4 | 4 | JOB_B10 | |
| 118 | spring体系 | springcloud | direct_support | 4 | 3 | JOB_B10 | |
| 119 | 分配职责 | 布置任务清晰 | direct_support | 4 | 4 | JOB_B10 | |
| 120 | 沟通表达与执行推进良好 | 沟通直接高效 | equivalent | 3 | 3 | JOB_B06 | |
| 121 | fpga | fpga工程师 | direct_support | 3 | 3 | JOB_B06 | |
| 122 | 与跨职能团队沟通协作 | 跨部门沟通协作（已完成） | direct_support | 3 | 3 | JOB_B06 | |
| 123 | 发挥影响力与担当 | 展现杰出专业能力和领导潜质 | direct_support | 3 | 2 | JOB_B06 | |
| 124 | 良好的沟通协调能力与质量意识 | 质量管理体系iso9001（已完成） | direct_support | 3 | 3 | JOB_B01 | |
| 125 | 良好的沟通协调能力与质量意识 | 跨部门沟通协作（已完成） | direct_support | 3 | 3 | JOB_B01 | |
| 126 | 良好的沟通协调能力与质量意识 | 沟通反馈正面 | equivalent | 3 | 3 | JOB_B01 | |
| 127 | 良好的沟通表达与执行推进能力 | 按时完成企业内控体系等任务，认真负责 | direct_support | 3 | 2 | JOB_B02 | |
| 128 | 输出数据分析报告 | python数据分析实战 | direct_support | 3 | 3 | JOB_B02 | |
| 129 | 输出数据分析报告 | 参与工业大数据分析平台 | direct_support | 3 | 3 | JOB_B02 | |
| 130 | 有erp系统 | 参与erp系统定制开发 | direct_support | 3 | 3 | JOB_B03 | |
| 131 | airflow | 涉及airflow等技术应用 | direct_support | 3 | 2 | JOB_B03 | |
| 132 | 薪酬体系设计与合规审计流程 | 负责方案设计，涉及岗评工具 | direct_support | 3 | 3 | JOB_B04 | |
| 133 | 薪酬体系设计与合规审计流程 | 参与薪酬体系改革，负责方案设计 | direct_support | 3 | 3 | JOB_B04 | |
| 134 | 有数字化平台项目管理与跨部门资源协调经验 | 项目「人力资源数字化平台」角色：协调人 | equivalent | 3 | 3 | JOB_B04 | |
| 135 | 较强的流程梳理与交付管理能力 | 流程梳理 | direct_support | 3 | 3 | JOB_B05 | |
| 136 | 较强的流程梳理与交付管理能力 | 成功交付全面预算管理等重大项目 | equivalent | 3 | 2 | JOB_B05 | |
| 137 | 较强的流程梳理与交付管理能力 | 较好完成流程再造工程交付 | equivalent | 3 | 2 | JOB_B05 | |
| 138 | 主导内控审计协调与流程梳理优化 | 企业内控体系建设，负责交付管理，涉及coso | direct_support | 3 | 2 | JOB_B05 | |
| 139 | 配合薪酬福利体系与人才盘点项目的内控支持 | 参与薪酬体系改革，负责资源协调 | direct_support | 3 | 2 | JOB_B05 | |
| 140 | 配合薪酬福利体系与人才盘点项目的内控支持 | 参与薪酬体系改革，负责流程优化 | direct_support | 3 | 2 | JOB_B05 | |
| 141 | 团队管理经验或潜力 | 管理渐入佳境 | direct_support | 3 | 3 | JOB_B07,JOB_B10 | |
| 142 | 主导业务数据分析 | python数据分析实战 | direct_support | 3 | 3 | JOB_B07 | |
| 143 | 可视化报表 | tableau | direct_support | 3 | 2 | JOB_B07 | |
| 144 | 主导业务数据分析 | 主导工业大数据分析项目 | direct_support | 3 | 2 | JOB_B07 | |
| 145 | 激励成员 | 为下属争取资源 | equivalent | 3 | 3 | JOB_B07 | |
| 146 | 薪酬 | 薪酬体系改革 | direct_support | 3 | 3 | JOB_B08 | |
| 147 | 培训 | 培训经理 | direct_support | 3 | 2 | JOB_B08,JOB_B09 | |
| 148 | 跨部门协调与团队管理行为能力突出 | 跨部门沟通协作（已完成） | direct_support | 3 | 3 | JOB_B08 | |
| 149 | 培训开发 | 岗位：培训经理 | direct_support | 3 | 3 | JOB_B08,JOB_B09 | |
| 150 | 绩效管理 | 绩效经理 | direct_support | 3 | 2 | JOB_B08,JOB_B09 | |
| 151 | 跨部门协调：主动沟通 | 跨部门沟通协作（已完成） | direct_support | 3 | 3 | JOB_B08 | |
| 152 | 拥抱挑战 | 负责技术攻关 | direct_support | 3 | 2 | JOB_B08 | |
| 153 | 持续学习新方法新工具并迁移到hr场景 | powerbi | direct_support | 3 | 2 | JOB_B08 | |
| 154 | 团队管理与执行推进可靠 | 主动承担团队责任 | direct_support | 3 | 3 | JOB_B09 | |
| 155 | 成长型思维与领导潜质者优先 | 有带团队潜力 | direct_support | 3 | 3 | JOB_B09 | |
| 156 | 激励成员 | 团队建设与激励 | direct_support | 3 | 3 | JOB_B09 | |
| 157 | 持续学习 | 培训：团队建设与激励（已完成） | direct_support | 3 | 3 | JOB_B09 | |
| 158 | 持续学习 | 培训：商业计划书撰写（已完成） | direct_support | 3 | 3 | JOB_B09 | |
| 159 | spring | springcloud | direct_support | 3 | 2 | JOB_B10 | |
| 160 | 团队管理经验或潜力 | 有带团队潜力；自然承担leader角色 | direct_support | 3 | 3 | JOB_B10 | |
| 161 | 带领研发小组：组建团队 | 自然承担leader角色 | equivalent | 3 | 3 | JOB_B10 | |
| 162 | 自我设定目标 | 目标管理与okr（已完成） | direct_support | 3 | 3 | JOB_B10 | |
| 163 | 持续推进 | 超额完成目标 | direct_support | 3 | 3 | JOB_B10 | |

## 第二部分：低频段（552 条，默认不入表）

| # | 要求侧词 | 证据侧词 | 关系 | 支持对数 | 核验（默认空） |
|---|----------|----------|------|----------|----------------|
| 1001 | 软件测试 | 测试工程师 | direct_support | 2 | |
| 1002 | 质量导向：标准合规 | 合规管理体系 | direct_support | 2 | |
| 1003 | 质量导向：标准合规 | 安全生产标准化培训 | direct_support | 2 | |
| 1004 | 沟通表达与执行推进良好 | 按时完成企业内控体系等任务，认真负责 | direct_support | 2 | |
| 1005 | 有领导潜质者优先 | 有带团队潜力 | equivalent | 2 | |
| 1006 | 沟通表达与执行推进良好 | 表现稳定，在薪酬体系改革中配合到位 | direct_support | 2 | |
| 1007 | 沟通表达与执行推进良好 | 参与薪酬体系改革项目，质量和进度符合预期 | direct_support | 2 | |
| 1008 | 有领导潜质者优先 | 领导力测评良好 | direct_support | 2 | |
| 1009 | 有领导潜质者优先 | 具备基层管理能力 | direct_support | 2 | |
| 1010 | 保障交付质量 | 岗位：质量工程师 | direct_support | 2 | |
| 1011 | 承担软件测试方案设计 | 岗位：测试工程师 | direct_support | 2 | |
| 1012 | 推动研发任务按期闭环交付 | 超额完成目标 | equivalent | 2 | |
| 1013 | 推动研发任务按期闭环交付 | 按时完成后端开发任务 | direct_support | 2 | |
| 1014 | 领导潜质发展通道 | 领导力发展工作坊（已完成） | direct_support | 2 | |
| 1015 | 发挥影响力与担当 | 发挥关键作用 | direct_support | 2 | |
| 1016 | 以骨干身份带动团队 | 角色：项目负责人 | direct_support | 2 | |
| 1017 | iso9001 | iso9001内审员证书 | direct_support | 2 | |
| 1018 | 良好的沟通协调能力与质量意识 | 质量和进度符合预期 | direct_support | 2 | |
| 1019 | 处理试制与交付过程中的质量问题闭环 | 质量过程控制与问题闭环改进 | direct_support | 2 | |
| 1020 | 智慧园区类项目的质量策划与评审 | 主导智慧园区工业iot质量监控平台质量工作 | direct_support | 2 | |
| 1021 | 数据处理与分析方法 | python数据分析实战 | direct_support | 2 | |
| 1022 | 数据处理与分析方法 | 数据可视化与报表（已完成） | direct_support | 2 | |
| 1023 | 数据处理与分析方法 | 方案设计，涉及powerbi | direct_support | 2 | |
| 1024 | 快速承担产品迭代中的关键任务 | 主导产品迭代v3项目攻克c++系统编程技术难题 | direct_support | 2 | |
| 1025 | 良好的沟通表达与执行推进能力 | 跨部门沟通协作 | direct_support | 2 | |
| 1026 | 良好的沟通表达与执行推进能力 | 较好完成云端迁移项目交付 | direct_support | 2 | |
| 1027 | 良好的沟通表达与执行推进能力 | 较好完成ai中台建设交付 | direct_support | 2 | |
| 1028 | 负责工业大数据分析平台的开发与优化 | 参与工业大数据分析平台，负责核心模块开发 | direct_support | 2 | |
| 1029 | 负责工业大数据分析平台的开发与优化 | 主导spark/flink调度链路建设 | direct_support | 2 | |
| 1030 | 负责工业大数据分析平台的开发与优化 | 参与工业大数据平台java微服务后端核心模块开发 | direct_support | 2 | |
| 1031 | 承担工业iot平台产品迭代开发中的关键模块 | 参与工业iot管理平台，负责核心模块开发 | equivalent | 2 | |
| 1032 | 承担工业iot平台产品迭代开发中的关键模块 | 参与边缘计算网关开发，负责技术攻关 | direct_support | 2 | |
| 1033 | 输出数据分析报告 | 较好完成工业大数据分析交付 | direct_support | 2 | |
| 1034 | 输出数据分析报告 | 攻克python数据分析技术难题 | direct_support | 2 | |
| 1035 | 输出数据分析报告 | 数据可视化与报表 | direct_support | 2 | |
| 1036 | 支撑制造过程改进决策 | 应用spc/fmea/8d质量工具开展质量过程控制与问题闭环改进 | direct_support | 2 | |
| 1037 | java及微服务架构 | 创新引入java微服务方案 | direct_support | 2 | |
| 1038 | java及微服务架构 | docker/springcloud/k8s | direct_support | 2 | |
| 1039 | java及微服务架构 | java/springboot微服务架构 | direct_support | 2 | |
| 1040 | 工业大数据平台开发经验者优先 | 工业iot管理平台 | equivalent | 2 | |
| 1041 | 工业大数据平台开发经验者优先 | 参与工业大数据分析平台，负责技术攻关 | direct_support | 2 | |
| 1042 | 工业大数据平台开发经验者优先 | 参与工业大数据分析平台，负责性能优化 | direct_support | 2 | |
| 1043 | 工业大数据平台开发经验者优先 | 工业大数据平台java微服务后端核心模块开发 | direct_support | 2 | |
| 1044 | 持有信息系统项目管理师或pmp认证者优先 | 培训：项目管理pmp认证（已完成） | direct_support | 2 | |
| 1045 | 负责erp系统定制开发与java微服务方案设计实现 | 参与erp系统定制开发，负责性能优化，涉及java等技术应用 | direct_support | 2 | |
| 1046 | 负责erp系统定制开发与java微服务方案设计实现 | 参与erp系统定制开发，负责核心模块开发，涉及java等技术应用 | direct_support | 2 | |
| 1047 | 负责erp系统定制开发与java微服务方案设计实现 | 参与erp系统定制开发，负责性能优化 | direct_support | 2 | |
| 1048 | 负责erp系统定制开发与java微服务方案设计实现 | 参与erp系统定制开发，负责核心模块开发，涉及java | direct_support | 2 | |
| 1049 | 负责erp系统定制开发与java微服务方案设计实现 | 担任erp系统后端架构师，负责java/springboot微服务架构 | direct_support | 2 | |
| 1050 | 承担工业大数据分析平台的数据集成与任务调度开发 | 担任工业大数据调度平台技术负责人，主导spark/flink调度链路建设 | direct_support | 2 | |
| 1051 | mqtt环境 | mqtt | direct_support | 2 | |
| 1052 | linux | linux部署 | direct_support | 2 | |
| 1053 | 主导跨系统集成项目的方案设计与进度管理 | 主导智慧园区平台项目 | direct_support | 2 | |
| 1054 | 薪酬体系设计与合规审计流程 | 成功交付薪酬体系改革 | direct_support | 2 | |
| 1055 | 薪酬体系设计与合规审计流程 | 参与薪酬体系改革项目 | direct_support | 2 | |
| 1056 | 有数字化平台项目管理与跨部门资源协调经验 | 主导云端迁移项目 | direct_support | 2 | |
| 1057 | 有数字化平台项目管理与跨部门资源协调经验 | 项目「人力资源数字化平台」角色：项目负责人 | direct_support | 2 | |
| 1058 | 有数字化平台项目管理与跨部门资源协调经验 | 参与人力资源数字化平台，负责交付管理 | direct_support | 2 | |
| 1059 | 有数字化平台项目管理与跨部门资源协调经验 | 担任人力资源数字化平台项目负责人 | direct_support | 2 | |
| 1060 | 持有中级会计师等职称者优先 | 证书：中级会计师 | direct_support | 2 | |
| 1061 | powerbi | 项目「人力资源数字化平台」角色：项目负责人；工具：excel/powerbi | direct_support | 2 | |
| 1062 | powerbi | 项目「人力资源数字化平台」角色：协调人；工具：powerbi | direct_support | 2 | |
| 1063 | 主导人力资源数字化平台建设与bi分析落地 | 担任人力资源数字化平台项目负责人，推进流程数字化落地 | equivalent | 2 | |
| 1064 | 负责薪酬体系改革方案设计与合规审计推动 | 参与薪酬体系改革，负责方案设计，涉及合规审计等技术应用 | direct_support | 2 | |
| 1065 | 负责薪酬体系改革方案设计与合规审计推动 | 项目「薪酬体系改革」角色：项目负责人；工具：岗评工具/excel/薪酬调研/合规审计 | direct_support | 2 | |
| 1066 | 主导方案设计与流程优化 | 项目负责人，负责方案设计与落地交付 | direct_support | 2 | |
| 1067 | coso内控框架与风险矩阵方法 | 涉及风险矩阵等技术应用 | direct_support | 2 | |
| 1068 | coso内控框架与风险矩阵方法 | 涉及coso等技术应用 | direct_support | 2 | |
| 1069 | coso内控框架与风险矩阵方法 | 工具：审计软件/流程梳理/风险矩阵/coso | direct_support | 2 | |
| 1070 | 较强的流程梳理与交付管理能力 | 项目管理pmp认证 | direct_support | 2 | |
| 1071 | 较强的流程梳理与交付管理能力 | 较好完成企业内控体系交付 | direct_support | 2 | |
| 1072 | 较强的流程梳理与交付管理能力 | 较好完成人才盘点项目交付 | direct_support | 2 | |
| 1073 | 较强的流程梳理与交付管理能力 | 在流程再造工程中发挥关键作用 | equivalent | 2 | |
| 1074 | 较强的流程梳理与交付管理能力 | 负责交付管理，涉及流程梳理 | direct_support | 2 | |
| 1075 | 持有高级会计师职称者优先 | 证书：高级会计师 | direct_support | 2 | |
| 1076 | coso框架 | coso | direct_support | 2 | |
| 1077 | 主导内控审计协调与流程梳理优化 | 参与企业内控体系建设，负责方案设计，涉及审计软件等技术应用 | direct_support | 2 | |
| 1078 | 主导内控审计协调与流程梳理优化 | 企业内控体系建设，负责交付管理，涉及审计软件 | direct_support | 2 | |
| 1079 | 主导内控审计协调与流程梳理优化 | 企业内控体系建设，负责交付管理，涉及流程梳理 | direct_support | 2 | |
| 1080 | 配合薪酬福利体系与人才盘点项目的内控支持 | 按时完成人才盘点项目等任务 | direct_support | 2 | |
| 1081 | 配合薪酬福利体系与人才盘点项目的内控支持 | 参与薪酬体系改革，负责方案设计，涉及合规审计等技术应用 | direct_support | 2 | |
| 1082 | 配合薪酬福利体系与人才盘点项目的内控支持 | 薪酬调研/合规审计 | direct_support | 2 | |
| 1083 | 配合薪酬福利体系与人才盘点项目的内控支持 | 参与薪酬体系改革，负责交付管理，涉及薪酬调研 | direct_support | 2 | |
| 1084 | 配合薪酬福利体系与人才盘点项目的内控支持 | 参与薪酬体系改革，负责交付管理，涉及合规审计 | direct_support | 2 | |
| 1085 | 数据分析完整能力链 | python数据分析实战（已完成） | direct_support | 2 | |
| 1086 | 数据分析完整能力链 | 攻克python数据分析技术难题 | direct_support | 2 | |
| 1087 | 可视化 | 数据可视化与报表 | direct_support | 2 | |
| 1088 | 交付 | 独立交付ok | direct_support | 2 | |
| 1089 | 交付 | 零缺陷交付记录 | direct_support | 2 | |
| 1090 | 交付 | 负责质量门禁机制交付 | direct_support | 2 | |
| 1091 | 交付 | 完成交付 | direct_support | 2 | |
| 1092 | 交付 | 高质量交付 | direct_support | 2 | |
| 1093 | 质量导向 | 质量意识强 | equivalent | 2 | |
| 1094 | 质量导向 | 高质量交付 | direct_support | 2 | |
| 1095 | bi | tableau | direct_support | 2 | |
| 1096 | 可视化报表 | 数据可视化与报表 | direct_support | 2 | |
| 1097 | 承担项目全生命周期管理：范围界定 | 项目管理pmp认证（已完成） | direct_support | 2 | |
| 1098 | 风险管理与交付验收 | 风险矩阵 | direct_support | 2 | |
| 1099 | 风险管理与交付验收 | 较好完成全面预算管理交付 | equivalent | 2 | |
| 1100 | 风险管理与交付验收 | 较好完成流程再造工程交付 | equivalent | 2 | |
| 1101 | 风险管理与交付验收 | 负责方案设计与落地交付 | equivalent | 2 | |
| 1102 | 快速吸收新技术并迁移应用到产品场景 | 主动学习前沿 | direct_support | 2 | |
| 1103 | 关注标准合规与可靠性 | 安全生产标准化培训（已完成） | direct_support | 2 | |
| 1104 | 关注标准合规与可靠性 | 参与合规管理提升项目 | direct_support | 2 | |
| 1105 | 关注标准合规与可靠性 | 合规审计 | direct_support | 2 | |
| 1106 | 关注标准合规与可靠性 | 企业内控体系建设 | direct_support | 2 | |
| 1107 | 薪酬 | 项目「薪酬体系改革」角色：核心成员 | direct_support | 2 | |
| 1108 | 薪酬 | 项目「薪酬体系改革」角色：协调人 | direct_support | 2 | |
| 1109 | 项目管理方法论 | 信息系统项目管理师 | equivalent | 2 | |
| 1110 | pmp | 项目管理pmp认证 | direct_support | 2 | |
| 1111 | 交付 | 参与数据治理专项并完成交付 | direct_support | 2 | |
| 1112 | 跨部门协调与团队管理行为能力突出 | 领导力发展工作坊（已完成） | direct_support | 2 | |
| 1113 | 学习敏捷 | 主动学习前沿 | equivalent | 2 | |
| 1114 | 绩效管理 | 培训：绩效管理实务（已完成）成绩96 | direct_support | 2 | |
| 1115 | 统筹人力资源规划 | 岗位：人力资源主管 | direct_support | 2 | |
| 1116 | 绩效管理 | 绩效管理实务（已完成）成绩86 | direct_support | 2 | |
| 1117 | 绩效管理 | 绩效管理实务（已完成）成绩88 | direct_support | 2 | |
| 1118 | 绩效管理 | 绩效管理实务（已完成）成绩69 | direct_support | 2 | |
| 1119 | 推动共识达成与信息同步 | 获得跨部门一致认可 | equivalent | 2 | |
| 1120 | 目标驱动达成 | 超额完成目标 | direct_support | 2 | |
| 1121 | 激励成员 | 团队建设与激励（已完成）成绩94 | direct_support | 2 | |
| 1122 | 绩效管理 | 绩效管理实务（已完成） | direct_support | 2 | |
| 1123 | 沟通表达出色 | 跨部门沟通顺畅 | equivalent | 2 | |
| 1124 | 书面表达 | 商业计划书撰写 | direct_support | 2 | |
| 1125 | 成长型思维与领导潜质者优先 | 领导力发展工作坊（已完成） | direct_support | 2 | |
| 1126 | 成长型思维与领导潜质者优先 | 能激发团队士气 | direct_support | 2 | |
| 1127 | 成长型思维与领导潜质者优先 | 具备基层管理能力 | direct_support | 2 | |
| 1128 | 协同人力资源体系：培训开发 | 培训：领导力发展工作坊（已完成） | direct_support | 2 | |
| 1129 | 组织发展落地 | 参与组织架构优化项目，负责方案设计 | direct_support | 2 | |
| 1130 | 组织发展落地 | 项目「组织架构优化项目」角色：协调人 | direct_support | 2 | |
| 1131 | 面向不同受众清晰表达与汇报 | 跨部门沟通协作（已完成） | direct_support | 2 | |
| 1132 | 持续学习 | 培训：新产品开发流程（已完成） | direct_support | 2 | |
| 1133 | 持续学习 | 培训：项目管理pmp认证（已完成） | direct_support | 2 | |
| 1134 | 持续学习 | 培训：职场英语提升（已完成） | direct_support | 2 | |
| 1135 | 持续学习 | 培训：供应链管理优化（已完成） | direct_support | 2 | |
| 1136 | 持续学习 | 培训：目标管理与okr（已完成） | direct_support | 2 | |
| 1137 | 领导潜质发展通道 | 领导力发展工作坊 | direct_support | 2 | |
| 1138 | 激励学员 | 团队建设与激励 | equivalent | 2 | |
| 1139 | 前后端 | django/react/postgresql/python | direct_support | 2 | |
| 1140 | 部署 | 负责java/springboot微服务架构与linux部署 | direct_support | 2 | |
| 1141 | 团队管理经验或潜力 | 自然承担leader角色；具备基层管理能力 | direct_support | 2 | |
| 1142 | 团队管理经验或潜力 | 有带团队潜力；领导力测评良好 | direct_support | 2 | |
| 1143 | 团队管理经验或潜力 | 有带团队潜力；具备基层管理能力 | direct_support | 2 | |
| 1144 | 团队管理经验或潜力 | 承担过负责人角色；具备基层管理能力 | direct_support | 2 | |
| 1145 | 团队管理经验或潜力 | 自然承担leader角色；领导力测评良好 | direct_support | 2 | |
| 1146 | 团队管理经验或潜力 | 团队建设与激励（已完成） | direct_support | 2 | |
| 1147 | 目标设定 | 目标管理与okr | equivalent | 2 | |
| 1148 | 主动承担 | 担任薪酬体系改革项目负责人 | direct_support | 2 | |
| 1149 | 带领研发小组：组建团队 | 担任薪酬体系改革项目负责人 | equivalent | 2 | |
| 1150 | 与产品/业务方沟通汇报 | 跨部门沟通协作（已完成） | direct_support | 2 | |
| 1151 | 推动版本按期闭环交付 | 较好完成产品迭代v3交付 | direct_support | 2 | |
| 1152 | 推动版本按期闭环交付 | 负责交付管理 | direct_support | 2 | |
| 1153 | 推动版本按期闭环交付 | 较好完成人才盘点项目交付 | direct_support | 2 | |
| 1154 | 推动版本按期闭环交付 | 成功交付全面预算管理等重大项目，获得跨部门一致认可 | direct_support | 2 | |
| 1155 | 嵌入式开发 | 嵌入式开发工程师 | direct_support | 1 | |
| 1156 | 质量导向：标准合规 | 安全合规加固 | direct_support | 1 | |
| 1157 | 质量导向：标准合规 | 合规审计 | direct_support | 1 | |
| 1158 | 可靠性 | 质量和进度符合预期 | equivalent | 1 | |
| 1159 | 过程规范 | 流程梳理 | direct_support | 1 | |
| 1160 | 可靠性 | 零缺陷交付记录 | direct_support | 1 | |
| 1161 | 可靠性 | 零缺陷交付 | direct_support | 1 | |
| 1162 | 过程规范 | spc/fmea/8d | direct_support | 1 | |
| 1163 | 可靠性 | 高质量交付 | equivalent | 1 | |
| 1164 | 学习敏捷性：快速学习新知识新技能 | 新技术上手 | direct_support | 1 | |
| 1165 | 学习敏捷性：快速学习新知识新技能 | 培训：职场英语提升（已完成）成绩98 | direct_support | 1 | |
| 1166 | 学习敏捷性：快速学习新知识新技能 | 培训：智能制造技术前沿（已完成）成绩93 | direct_support | 1 | |
| 1167 | 学习敏捷性：快速学习新知识新技能 | 学习速度快；快速查资料 | equivalent | 1 | |
| 1168 | 学习敏捷性：快速学习新知识新技能 | 培训：人工智能基础与应用（已完成）成绩73 | direct_support | 1 | |
| 1169 | 学习敏捷性：快速学习新知识新技能 | 主动学习前 | equivalent | 1 | |
| 1170 | 学习敏捷性：快速学习新知识新技能 | 培训：人工智能基础与应用（已完成）成绩82 | direct_support | 1 | |
| 1171 | 学习敏捷性：快速学习新知识新技能 | 培训：创新思维与triz方法（已完成）成绩95 | direct_support | 1 | |
| 1172 | 学习敏捷性：快速学习新知识新技能 | 培训：智能制造技术前沿（已完成）成绩69 | direct_support | 1 | |
| 1173 | 学习敏捷性：快速学习新知识新技能 | 学习速 | equivalent | 1 | |
| 1174 | 学习敏捷性：快速学习新知识新技能 | 培训：人工智能基础与应用（已完成）成绩88 | direct_support | 1 | |
| 1175 | 学习敏捷性：快速学习新知识新技能 | 培训：新产品开发流程（已完成）成绩88 | direct_support | 1 | |
| 1176 | 学习敏捷性：快速学习新知识新技能 | 培训：数字化转型战略（已完成）成绩71 | direct_support | 1 | |
| 1177 | 学习敏捷性：快速学习新知识新技能 | 培训：数字化转型战略（已完成）成绩88 | direct_support | 1 | |
| 1178 | 学习敏捷性：快速学习新知识新技能 | 快速掌握新调度框架 | direct_support | 1 | |
| 1179 | 沟通表达与执行推进良好 | 工作态度端正，较好完成薪酬体系改革交付 | direct_support | 1 | |
| 1180 | 沟通表达与执行推进良好 | 按时完成合规管理提升等任务，认真负责 | direct_support | 1 | |
| 1181 | 沟通表达与执行推进良好 | 较好完成人才盘点项目交付 | direct_support | 1 | |
| 1182 | 沟通表达与执行推进良好 | 完成合规管理提升等任务无重大失误，日常表现踏实 | direct_support | 1 | |
| 1183 | 沟通表达与执行推进良好 | 表现稳定，在人才盘点项目中配合到位 | direct_support | 1 | |
| 1184 | 沟通表达与执行推进良好 | 参与流程再造工程项目，质量和进度符合预期 | direct_support | 1 | |
| 1185 | 沟通表达与执行推进良好 | 表现稳定，在流程再造工程中配合到位 | direct_support | 1 | |
| 1186 | 沟通表达与执行推进良好 | 完成企业内控体系等任务无重大失误，日常表现踏实 | direct_support | 1 | |
| 1187 | 沟通表达与执行推进良好 | 创新引入风险管控方案，效率提升超30% | direct_support | 1 | |
| 1188 | 沟通表达与执行推进良好 | 参与全面预算管理项目，质量和进度符合预期 | direct_support | 1 | |
| 1189 | 沟通表达与执行推进良好 | 较好完成组织架构优化交付 | direct_support | 1 | |
| 1190 | 沟通表达与执行推进良好 | 表现稳定，在全面预算管理中配合到位 | direct_support | 1 | |
| 1191 | 沟通表达与执行推进良好 | 成功交付全面预算管理等重大项目，获得跨部门一致认可 | direct_support | 1 | |
| 1192 | 沟通表达与执行推进良好 | 参与合规管理提升项目，质量和进度符合预期 | direct_support | 1 | |
| 1193 | 沟通表达与执行推进良好 | 较好完成全面预算管理交付 | direct_support | 1 | |
| 1194 | 沟通表达与执行推进良好 | 较好完成流程再造工程交付 | direct_support | 1 | |
| 1195 | 沟通表达与执行推进良好 | 口头表达清晰；沟通直接高效 | equivalent | 1 | |
| 1196 | 沟通表达与执行推进良好 | 口头表达清晰，主导跨部门质量评审 | equivalent | 1 | |
| 1197 | 沟通表达与执行推进良好 | 沟通高效，协作顺畅 | equivalent | 1 | |
| 1198 | fpga | 岗位：fpga工程师 | direct_support | 1 | |
| 1199 | 保障交付质量 | 质量管理体系iso9001（已完成） | direct_support | 1 | |
| 1200 | 推动过程规范与持续改进 | 应用spc/fmea/8d质量工具开展质量过程控制与问题闭环改进 | direct_support | 1 | |
| 1201 | 推动过程规范与持续改进 | 质量过程控制与问题闭环改进 | direct_support | 1 | |
| 1202 | 推动研发任务按期闭环交付 | 按时完成erp核心升级等任务 | equivalent | 1 | |
| 1203 | 推动研发任务按期闭环交付 | 较好完成工业大数据分析交付 | equivalent | 1 | |
| 1204 | 推动研发任务按期闭环交付 | 质量和进度符合预期 | equivalent | 1 | |
| 1205 | 推动研发任务按期闭环交付 | 较好完成产品迭代v3交付 | equivalent | 1 | |
| 1206 | 推动研发任务按期闭环交付 | 较好完成云端迁移项目交付 | equivalent | 1 | |
| 1207 | 推动研发任务按期闭环交付 | 较好完成erp核心升级交付 | equivalent | 1 | |
| 1208 | 推动研发任务按期闭环交付 | 较好完成ai中台建设交付 | equivalent | 1 | |
| 1209 | 推动研发任务按期闭环交付 | 按时完成ai中台建设等任务 | direct_support | 1 | |
| 1210 | 推动研发任务按期闭环交付 | 按时完成流程再造工程等任务 | direct_support | 1 | |
| 1211 | 与跨职能团队沟通协作 | 主导跨部门质量评审 | direct_support | 1 | |
| 1212 | 推动研发任务按期闭环交付 | 按时完成调度平台建设任务 | direct_support | 1 | |
| 1213 | 与跨职能团队沟通协作 | 沟通高效，协作顺畅 | equivalent | 1 | |
| 1214 | 推动研发任务按期闭环交付 | 落地交付 | equivalent | 1 | |
| 1215 | 以骨干身份带动团队 | 具备基层管理能力 | direct_support | 1 | |
| 1216 | 以骨干身份带动团队 | 培训：团队建设与激励（已完成） | direct_support | 1 | |
| 1217 | 发挥影响力与担当 | 主动承担责任 | direct_support | 1 | |
| 1218 | 发挥影响力与担当 | 能激发团队士气；领导力测评良好；关键时刻能兜底 | direct_support | 1 | |
| 1219 | 以骨干身份带动团队 | 担任工业大数据调度平台技术负责人 | direct_support | 1 | |
| 1220 | 以骨干身份带动团队 | 承担负责人角色，具备基层管理能力 | direct_support | 1 | |
| 1221 | 以骨干身份带动团队 | 担任薪酬体系改革项目负责人 | direct_support | 1 | |
| 1222 | spc | spc/fmea/8d质量工具 | direct_support | 1 | |
| 1223 | fmea | spc/fmea/8d | direct_support | 1 | |
| 1224 | 智慧园区 | 智慧园区工业iot质量监控平台 | direct_support | 1 | |
| 1225 | 智慧园区 | 主导智慧园区工业iot质量监控平台质量工作 | direct_support | 1 | |
| 1226 | 良好的沟通协调能力与质量意识 | 沟通直接高效 | equivalent | 1 | |
| 1227 | 良好的沟通协调能力与质量意识 | 质量意识强，零缺陷交付记录 | direct_support | 1 | |
| 1228 | 良好的沟通协调能力与质量意识 | 零缺陷交付，质量监控平台质量门禁落地 | direct_support | 1 | |
| 1229 | 良好的沟通协调能力与质量意识 | 沟通高效，协作顺畅 | direct_support | 1 | |
| 1230 | 负责智能制造平台类项目的全过程质量管控与验收 | 主导智慧园区工业iot质量监控平台质量工作，负责质量门禁机制交付 | direct_support | 1 | |
| 1231 | 负责智能制造平台类项目的全过程质量管控与验收 | 项目「智慧园区工业iot质量监控平台」角色：质量负责人 | direct_support | 1 | |
| 1232 | 主导质量管理体系建设 | 应用spc/fmea/8d质量工具开展质量过程控制与问题闭环改进 | direct_support | 1 | |
| 1233 | 数据处理与分析方法 | spark/python/tableau/hadoop | direct_support | 1 | |
| 1234 | 数据处理与分析方法 | 攻克python数据分析技术难题 | direct_support | 1 | |
| 1235 | 数据处理与分析方法 | 涉及tableau等技术应用 | direct_support | 1 | |
| 1236 | 数据处理与分析方法 | python/hadoop/spark/tableau | direct_support | 1 | |
| 1237 | 数据处理与分析方法 | python数据分析实战（已完成） | direct_support | 1 | |
| 1238 | 数据处理与分析方法 | powerbi/excel | direct_support | 1 | |
| 1239 | 数据处理与分析方法 | sql/excel/用友nc/bi报表 | direct_support | 1 | |
| 1240 | 数据处理与分析方法 | powerbi/saphr/oa/excel | direct_support | 1 | |
| 1241 | 数据处理与分析方法 | bi报表/用友nc/excel/sql | direct_support | 1 | |
| 1242 | 数据处理与分析方法 | 方案设计，涉及sql | direct_support | 1 | |
| 1243 | 数据处理与分析方法 | 资源协调，涉及powerbi | direct_support | 1 | |
| 1244 | 数据处理与分析方法 | 协调，涉及powerbi | direct_support | 1 | |
| 1245 | 数据处理与分析方法 | 方案设计，涉及bi报表 | direct_support | 1 | |
| 1246 | 大数据平台调度工具 | spark/flink调度链路建设 | direct_support | 1 | |
| 1247 | 大数据平台调度工具 | spark/flink | direct_support | 1 | |
| 1248 | 快速承担产品迭代中的关键任务 | 在产品迭代v3中发挥关键作用 | direct_support | 1 | |
| 1249 | 快速承担产品迭代中的关键任务 | 主导工业大数据分析项目攻克ai算法技术难题 | direct_support | 1 | |
| 1250 | 学习能力强 | 新产品开发流程（已完成）成绩88 | direct_support | 1 | |
| 1251 | 学习能力强 | 学习速度快，快速掌握新调度框架 | equivalent | 1 | |
| 1252 | 学习能力强 | 学习速度快，钻研新技术栈 | equivalent | 1 | |
| 1253 | 良好的沟通表达与执行推进能力 | 按时完成erp核心升级等任务 | direct_support | 1 | |
| 1254 | 良好的沟通表达与执行推进能力 | 较好完成erp核心升级交付 | direct_support | 1 | |
| 1255 | 良好的沟通表达与执行推进能力 | 较好完成产品迭代v3交付 | direct_support | 1 | |
| 1256 | 良好的沟通表达与执行推进能力 | 超额完成目标 | direct_support | 1 | |
| 1257 | 良好的沟通表达与执行推进能力 | 较好完成工业大数据分析交付 | direct_support | 1 | |
| 1258 | 良好的沟通表达与执行推进能力 | 按时完成ai中台建设等任务 | direct_support | 1 | |
| 1259 | 良好的沟通表达与执行推进能力 | 较好完成薪酬体系改革交付 | direct_support | 1 | |
| 1260 | 良好的沟通表达与执行推进能力 | 按时完成合规管理提升等任务，认真负责 | direct_support | 1 | |
| 1261 | 良好的沟通表达与执行推进能力 | 较好完成人才盘点项目交付 | direct_support | 1 | |
| 1262 | 良好的沟通表达与执行推进能力 | 沟通高效，协作顺畅 | direct_support | 1 | |
| 1263 | 良好的沟通表达与执行推进能力 | 按时完成薪酬改革任务 | direct_support | 1 | |
| 1264 | 良好的沟通表达与执行推进能力 | 较好完成薪酬体系落地 | direct_support | 1 | |
| 1265 | 负责工业大数据分析平台的开发与优化 | 参与工业大数据分析平台，负责技术攻关 | equivalent | 1 | |
| 1266 | 输出数据分析报告 | 参与工业大数据分析项目 | direct_support | 1 | |
| 1267 | 输出数据分析报告 | 参与工业大数据分析项目，质量和进度符合预期 | direct_support | 1 | |
| 1268 | 输出数据分析报告 | 主导工业大数据分析项目 | direct_support | 1 | |
| 1269 | 输出数据分析报告 | 主导工业大数据分析项目攻克ai算法技术难题 | direct_support | 1 | |
| 1270 | 输出数据分析报告 | 在工业大数据分析中配合到位 | direct_support | 1 | |
| 1271 | 输出数据分析报告 | bi报表/用友nc/sql/excel | direct_support | 1 | |
| 1272 | 输出数据分析报告 | 负责报告撰写 | direct_support | 1 | |
| 1273 | linux环境部署 | 涉及linux等技术应用 | direct_support | 1 | |
| 1274 | linux环境部署 | mqtt/linux/嵌入式/c++ | direct_support | 1 | |
| 1275 | java及微服务架构 | mysql/java/k8s/docker | direct_support | 1 | |
| 1276 | linux环境部署 | mqtt/c++/嵌入式/linux | direct_support | 1 | |
| 1277 | java及微服务架构 | java/springcloud/docker | direct_support | 1 | |
| 1278 | java及微服务架构 | springcloud/java | direct_support | 1 | |
| 1279 | linux环境部署 | linux | direct_support | 1 | |
| 1280 | 有erp系统 | 参与erp系统定制开发，负责核心模块开发 | direct_support | 1 | |
| 1281 | 有erp系统 | 较好完成erp核心升级交付 | direct_support | 1 | |
| 1282 | 工业大数据平台开发经验者优先 | 参与工业大数据分析平台，负责核心模块开发 | direct_support | 1 | |
| 1283 | 有erp系统 | 参与erp系统定制开发，负责代码审查 | direct_support | 1 | |
| 1284 | 有erp系统 | 参与erp系统定制开发，负责技术攻关 | direct_support | 1 | |
| 1285 | 工业大数据平台开发经验者优先 | 工业大数据调度平台技术负责人 | direct_support | 1 | |
| 1286 | 有erp系统 | 担任erp系统后端架构师 | direct_support | 1 | |
| 1287 | 持有信息系统项目管理师或pmp认证者优先 | 证书：pmp | direct_support | 1 | |
| 1288 | 持有信息系统项目管理师或pmp认证者优先 | 信息系统项目管理师 | direct_support | 1 | |
| 1289 | 持有信息系统项目管理师或pmp认证者优先 | 证书：hr管理师、pmp | direct_support | 1 | |
| 1290 | 负责erp系统定制开发与java微服务方案设计实现 | 创新引入java微服务方案 | direct_support | 1 | |
| 1291 | airflow | 工具：python/spark/hadoop/airflow | direct_support | 1 | |
| 1292 | linux | mqtt/linux | direct_support | 1 | |
| 1293 | linux | linux/c++/mqtt | direct_support | 1 | |
| 1294 | 薪酬体系设计与合规审计流程 | 薪酬调研/合规审计 | direct_support | 1 | |
| 1295 | 薪酬体系设计与合规审计流程 | 薪酬体系改革，负责资源协调 | direct_support | 1 | |
| 1296 | 薪酬体系设计与合规审计流程 | 负责交付管理，涉及合规审计 | direct_support | 1 | |
| 1297 | 薪酬体系设计与合规审计流程 | 薪酬体系改革，负责交付管理 | direct_support | 1 | |
| 1298 | 薪酬体系设计与合规审计流程 | 负责报告撰写，涉及合规审计 | direct_support | 1 | |
| 1299 | 薪酬体系设计与合规审计流程 | 较好完成薪酬体系改革交付 | direct_support | 1 | |
| 1300 | 薪酬体系设计与合规审计流程 | 负责方案设计，涉及合规审计 | direct_support | 1 | |
| 1301 | 薪酬体系设计与合规审计流程 | 在薪酬体系改革中配合到位 | direct_support | 1 | |
| 1302 | 薪酬体系设计与合规审计流程 | 薪酬体系设计方案 | equivalent | 1 | |
| 1303 | 薪酬体系设计与合规审计流程 | 参与薪酬体系改革，负责交付管理，涉及合规审计 | direct_support | 1 | |
| 1304 | 薪酬体系设计与合规审计流程 | 薪酬体系改革项目负责人，负责方案设计 | direct_support | 1 | |
| 1305 | 薪酬体系设计与合规审计流程 | 担任薪酬体系改革项目负责人，负责方案设计与落地交付 | direct_support | 1 | |
| 1306 | 有数字化平台项目管理与跨部门资源协调经验 | 主导智慧园区平台项目攻克docker容器化技术难题 | direct_support | 1 | |
| 1307 | 主导人力资源数字化平台建设与bi分析落地 | 项目「人力资源数字化平台」角色：项目负责人；工具：powerbi/oa/excel/saphr | direct_support | 1 | |
| 1308 | powerbi | 参与人力资源数字化平台，负责方案设计，涉及powerbi | direct_support | 1 | |
| 1309 | powerbi | 项目「人力资源数字化平台」角色：核心成员；工具：powerbi | direct_support | 1 | |
| 1310 | powerbi | 参与人力资源数字化平台，负责资源协调，涉及powerbi | direct_support | 1 | |
| 1311 | powerbi | 项目「人力资源数字化平台」角色：协调人；工具：saphr/oa/excel/powerbi | direct_support | 1 | |
| 1312 | 负责薪酬体系改革方案设计与合规审计推动 | 负责交付管理，涉及合规审计等技术应用 | direct_support | 1 | |
| 1313 | 负责薪酬体系改革方案设计与合规审计推动 | 项目「薪酬体系改革」角色：项目负责人；工具：岗评工具/薪酬调研/excel/合规审计 | direct_support | 1 | |
| 1314 | 负责薪酬体系改革方案设计与合规审计推动 | 项目「薪酬体系改革」角色：项目负责人；工具：合规审计/薪酬调研/excel/岗评工具 | direct_support | 1 | |
| 1315 | 负责薪酬体系改革方案设计与合规审计推动 | 担任薪酬体系改革项目负责人，负责方案设计与落地交付 | direct_support | 1 | |
| 1316 | 负责薪酬体系改革方案设计与合规审计推动 | 项目「薪酬体系改革」角色：项目负责人；工具：薪酬设计；担任薪酬体系改革项目负责人，负责方案设计与落地交付 | direct_support | 1 | |
| 1317 | 主导方案设计与流程优化 | 主导产品迭代v3项目攻克c++系统编程技术难题 | direct_support | 1 | |
| 1318 | 主导方案设计与流程优化 | 主导工业大数据分析项目攻克ai算法技术难题 | direct_support | 1 | |
| 1319 | 主导方案设计与流程优化 | 主导云端迁移项目项目攻克python数据分析技术难题 | direct_support | 1 | |
| 1320 | coso内控框架与风险矩阵方法 | 风险矩阵/审计软件/coso/流程梳理 | direct_support | 1 | |
| 1321 | coso内控框架与风险矩阵方法 | 审计软件/coso/流程梳理/风险矩阵 | direct_support | 1 | |
| 1322 | coso内控框架与风险矩阵方法 | 审计软件/风险矩阵/coso/流程梳理 | direct_support | 1 | |
| 1323 | coso内控框架与风险矩阵方法 | 参与企业内控体系建设，负责方案设计，涉及coso等技术应用 | direct_support | 1 | |
| 1324 | coso内控框架与风险矩阵方法 | coso/审计软件/流程梳理/风险矩阵 | direct_support | 1 | |
| 1325 | coso内控框架与风险矩阵方法 | 参与企业内控体系建设，负责资源协调，涉及coso等技术应用 | direct_support | 1 | |
| 1326 | coso内控框架与风险矩阵方法 | 风险矩阵/流程梳理/coso/审计软件 | direct_support | 1 | |
| 1327 | coso内控框架与风险矩阵方法 | 工具：风险矩阵/流程梳理/审计软件/coso | direct_support | 1 | |
| 1328 | coso内控框架与风险矩阵方法 | 工具：coso/审计软件/流程梳理/风险矩阵 | direct_support | 1 | |
| 1329 | coso内控框架与风险矩阵方法 | 工具：coso/风险矩阵/审计软件/流程梳理 | direct_support | 1 | |
| 1330 | coso内控框架与风险矩阵方法 | 工具：coso/审计软件/风险矩阵/流程梳理 | direct_support | 1 | |
| 1331 | coso内控框架与风险矩阵方法 | 工具：流程梳理/风险矩阵/审计软件/coso | direct_support | 1 | |
| 1332 | 较强的流程梳理与交付管理能力 | 较好完成ai中台建设交付 | direct_support | 1 | |
| 1333 | 较强的流程梳理与交付管理能力 | 按时完成ai中台建设等任务 | direct_support | 1 | |
| 1334 | 较强的流程梳理与交付管理能力 | 成功交付薪酬体系改革等重大项目 | direct_support | 1 | |
| 1335 | 较强的流程梳理与交付管理能力 | 负责流程优化 | direct_support | 1 | |
| 1336 | 较强的流程梳理与交付管理能力 | 成功交付流程再造工程等重大项目 | equivalent | 1 | |
| 1337 | 较强的流程梳理与交付管理能力 | 质量意识强，零缺陷交付记录 | equivalent | 1 | |
| 1338 | 较强的流程梳理与交付管理能力 | 负责方案设计与落地交付 | direct_support | 1 | |
| 1339 | 负责企业内控体系建设项目统筹与协调 | 项目「企业内控体系建设」角色：协调人 | direct_support | 1 | |
| 1340 | 负责企业内控体系建设项目统筹与协调 | 参与企业内控体系建设，负责方案设计 | direct_support | 1 | |
| 1341 | 风险矩阵 | 工具：审计软件/coso/流程梳理/风险矩阵 | direct_support | 1 | |
| 1342 | coso框架 | 工具：审计软件/风险矩阵/coso/流程梳理 | direct_support | 1 | |
| 1343 | coso框架 | 参与企业内控体系建设，负责方案设计，涉及coso | direct_support | 1 | |
| 1344 | coso框架 | 参与企业内控体系建设，负责资源协调，涉及coso | direct_support | 1 | |
| 1345 | 负责企业内控体系建设项目统筹与协调 | 项目「企业内控体系建设」角色：项目负责人 | direct_support | 1 | |
| 1346 | 主导内控审计协调与流程梳理优化 | 按时完成企业内控体系等任务 | direct_support | 1 | |
| 1347 | 主导内控审计协调与流程梳理优化 | 参与企业内控体系建设，负责资源协调，涉及审计软件等技术应用 | direct_support | 1 | |
| 1348 | 主导内控审计协调与流程梳理优化 | 2025年参与企业内控体系项目 | direct_support | 1 | |
| 1349 | 主导内控审计协调与流程梳理优化 | 较好完成企业内控体系交付 | direct_support | 1 | |
| 1350 | 主导内控审计协调与流程梳理优化 | 按时完成企业内控体系交付 | direct_support | 1 | |
| 1351 | 主导内控审计协调与流程梳理优化 | 项目「企业内控体系建设」角色：协调人 | direct_support | 1 | |
| 1352 | 主导内控审计协调与流程梳理优化 | 参与企业内控体系建设，负责方案设计，涉及coso等技术应用 | direct_support | 1 | |
| 1353 | 主导内控审计协调与流程梳理优化 | 项目「企业内控体系建设」角色：项目负责人 | direct_support | 1 | |
| 1354 | 主导内控审计协调与流程梳理优化 | 参与企业内控体系建设，负责资源协调，涉及coso等技术应用 | direct_support | 1 | |
| 1355 | 主导内控审计协调与流程梳理优化 | 企业内控体系建设，负责报告撰写，涉及风险矩阵 | direct_support | 1 | |
| 1356 | 主导内控审计协调与流程梳理优化 | 企业内控体系建设，负责资源协调，涉及风险矩阵 | direct_support | 1 | |
| 1357 | 配合薪酬福利体系与人才盘点项目的内控支持 | 工具：excel/岗评工具/薪酬调研/合规审计 | direct_support | 1 | |
| 1358 | 配合薪酬福利体系与人才盘点项目的内控支持 | 参与薪酬体系改革，负责交付管理，涉及合规审计等技术应用 | direct_support | 1 | |
| 1359 | 配合薪酬福利体系与人才盘点项目的内控支持 | 参与薪酬体系改革，负责报告撰写，涉及合规审计等技术应用 | direct_support | 1 | |
| 1360 | 配合薪酬福利体系与人才盘点项目的内控支持 | 工具：excel/合规审计/岗评工具/薪酬调研 | direct_support | 1 | |
| 1361 | 配合薪酬福利体系与人才盘点项目的内控支持 | 较好完成人才盘点项目交付 | direct_support | 1 | |
| 1362 | 配合薪酬福利体系与人才盘点项目的内控支持 | 在薪酬体系改革中配合到位 | direct_support | 1 | |
| 1363 | 配合薪酬福利体系与人才盘点项目的内控支持 | 参与薪酬体系改革，负责方案设计 | direct_support | 1 | |
| 1364 | 配合薪酬福利体系与人才盘点项目的内控支持 | 参与薪酬体系改革，负责报告撰写 | direct_support | 1 | |
| 1365 | 配合薪酬福利体系与人才盘点项目的内控支持 | 2025年成功交付人才盘点项目等重大项目 | direct_support | 1 | |
| 1366 | 配合薪酬福利体系与人才盘点项目的内控支持 | 参与薪酬体系改革，负责资源协调，涉及岗评工具 | direct_support | 1 | |
| 1367 | 配合薪酬福利体系与人才盘点项目的内控支持 | 参与薪酬体系改革，负责流程优化，涉及岗评工具 | direct_support | 1 | |
| 1368 | 配合薪酬福利体系与人才盘点项目的内控支持 | 在人才盘点项目中发挥关键作用 | direct_support | 1 | |
| 1369 | 配合薪酬福利体系与人才盘点项目的内控支持 | 参与薪酬体系改革项目，质量和进度符合预期 | direct_support | 1 | |
| 1370 | 配合薪酬福利体系与人才盘点项目的内控支持 | 在人才盘点项目中配合到位 | direct_support | 1 | |
| 1371 | 使用审计软件开展内控测试与整改跟踪 | 工具：审计软件/流程梳理/风险矩阵/coso | direct_support | 1 | |
| 1372 | 使用审计软件开展内控测试与整改跟踪 | 流程梳理/风险矩阵/审计软件/coso | direct_support | 1 | |
| 1373 | sql | mysql | direct_support | 1 | |
| 1374 | sql | postgresql | direct_support | 1 | |
| 1375 | 数据分析完整能力链 | python数据分析实战 | direct_support | 1 | |
| 1376 | sql | 涉及sql等技术应用 | direct_support | 1 | |
| 1377 | sql | pandas/sql日常取数建模 | direct_support | 1 | |
| 1378 | sql | pandas/sql日常取数建模支撑 | direct_support | 1 | |
| 1379 | 风险管理 | 风险管控方案 | direct_support | 1 | |
| 1380 | 交付 | 企业内控体系交付 | direct_support | 1 | |
| 1381 | 交付 | 成功交付薪酬体系改革 | direct_support | 1 | |
| 1382 | 交付 | 人才盘点项目交付 | direct_support | 1 | |
| 1383 | 交付 | 成功交付 | direct_support | 1 | |
| 1384 | 交付 | 管理交付 | direct_support | 1 | |
| 1385 | pmp | 信息系统项目管理师 | equivalent | 1 | |
| 1386 | 交付 | 落地交付 | direct_support | 1 | |
| 1387 | 交付 | 负责方案设计与落地交付 | direct_support | 1 | |
| 1388 | 执行推进与学习敏捷性突出 | 学习速度快 | equivalent | 1 | |
| 1389 | 团队管理经验或潜力 | 团队建设与激励 | direct_support | 1 | |
| 1390 | 质量导向 | 质量意识强，零缺陷交付记录 | equivalent | 1 | |
| 1391 | 质量导向 | 质量过程控制与问题闭环改进 | direct_support | 1 | |
| 1392 | 质量导向 | 零缺陷交付 | direct_support | 1 | |
| 1393 | 执行推进与学习敏捷性突出 | 学习速度快，快速掌握新调度框架 | direct_support | 1 | |
| 1394 | 执行推进与学习敏捷性突出 | 学习速度快，钻研新技术栈 | direct_support | 1 | |
| 1395 | 主导业务数据分析 | 工业大数据分析项目 | direct_support | 1 | |
| 1396 | 主导业务数据分析 | python数据分析技术难题 | direct_support | 1 | |
| 1397 | 主导业务数据分析 | 主导spark/flink调度链路建设，pandas/sql日常取数建模支撑 | direct_support | 1 | |
| 1398 | 风险管理与交付验收 | 较好完成工业大数据分析交付 | direct_support | 1 | |
| 1399 | 风险管理与交付验收 | 较好完成云端迁移项目交付 | direct_support | 1 | |
| 1400 | 风险管理与交付验收 | 负责方案设计 | direct_support | 1 | |
| 1401 | 风险管理与交付验收 | 创新引入风险管控方案 | direct_support | 1 | |
| 1402 | 风险管理与交付验收 | 较好完成企业内控体系交付 | direct_support | 1 | |
| 1403 | 风险管理与交付验收 | 成功交付薪酬体系改革等重大项目 | direct_support | 1 | |
| 1404 | 风险管理与交付验收 | 涉及coso等技术应用 | direct_support | 1 | |
| 1405 | 风险管理与交付验收 | 成功交付全面预算管理等重大项目 | equivalent | 1 | |
| 1406 | 进度控制 | 按时完成流程再造工程等任务 | equivalent | 1 | |
| 1407 | 风险管理与交付验收 | 参与数据治理专项并完成交付 | equivalent | 1 | |
| 1408 | 风险管理与交付验收 | 数据治理专项高质量交付 | equivalent | 1 | |
| 1409 | 组建与管理研发小组：分配职责 | 领导力发展工作坊（已完成） | equivalent | 1 | |
| 1410 | 组建与管理研发小组：分配职责 | 角色：技术负责人 | direct_support | 1 | |
| 1411 | 关注标准合规与可靠性 | 质量和进度符合预期 | direct_support | 1 | |
| 1412 | 关注标准合规与可靠性 | 完成安全合规加固等任务无重大失误 | direct_support | 1 | |
| 1413 | 关注标准合规与可靠性 | 质量意识强 | direct_support | 1 | |
| 1414 | 关注标准合规与可靠性 | 安全合规加固项目，质量和进度符合预期 | direct_support | 1 | |
| 1415 | 关注标准合规与可靠性 | 参与安全合规加固项目，质量和进度符合预期 | direct_support | 1 | |
| 1416 | 快速吸收新技术并迁移应用到产品场景 | 创新引入云计算方案 | direct_support | 1 | |
| 1417 | 关注标准合规与可靠性 | 参与企业内控体系等任务 | direct_support | 1 | |
| 1418 | 关注标准合规与可靠性 | 参与企业内控体系项目 | direct_support | 1 | |
| 1419 | 关注标准合规与可靠性 | 涉及coso等技术应用 | direct_support | 1 | |
| 1420 | 关注标准合规与可靠性 | 参与企业内控体系建设 | direct_support | 1 | |
| 1421 | 关注标准合规与可靠性 | 项目「企业内控体系建设」 | direct_support | 1 | |
| 1422 | 关注标准合规与可靠性 | 在合规管理提升中配合到位 | direct_support | 1 | |
| 1423 | 关注标准合规与可靠性 | 在合规管理提升中发挥关键作用 | direct_support | 1 | |
| 1424 | 关注标准合规与可靠性 | 零缺陷交付，质量监控平台质量门禁落地 | direct_support | 1 | |
| 1425 | 快速吸收新技术并迁移应用到产品场景 | 学习速度快，快速掌握新调度框架 | direct_support | 1 | |
| 1426 | 快速吸收新技术并迁移应用到产品场景 | 学习速度快，钻研新技术栈 | direct_support | 1 | |
| 1427 | 培训 | 培训：企业文化建设（已完成） | direct_support | 1 | |
| 1428 | 培训 | 培训：目标管理与okr（已完成） | direct_support | 1 | |
| 1429 | 薪酬 | 参与薪酬体系改革 | direct_support | 1 | |
| 1430 | 薪酬 | 参与薪酬体系改革，负责交付管理 | direct_support | 1 | |
| 1431 | 薪酬 | 参与薪酬体系改革，负责报告撰写 | direct_support | 1 | |
| 1432 | 薪酬 | 参与薪酬体系改革，负责方案设计 | direct_support | 1 | |
| 1433 | 组织发展 | 培训：团队建设与激励（已完成） | direct_support | 1 | |
| 1434 | 薪酬 | 参与薪酬体系改革项目 | direct_support | 1 | |
| 1435 | 薪酬 | 参与薪酬体系改革，负责资源协调 | direct_support | 1 | |
| 1436 | 薪酬 | 项目「薪酬体系改革」角色：执行人 | direct_support | 1 | |
| 1437 | 组织发展 | 参与组织架构优化项目，负责流程优化 | direct_support | 1 | |
| 1438 | 组织发展 | 组织架构优化项目 | direct_support | 1 | |
| 1439 | 招聘 | 招聘主管 | direct_support | 1 | |
| 1440 | 薪酬 | 薪酬福利专员 | direct_support | 1 | |
| 1441 | 薪酬 | 薪酬体系改革项目负责人 | direct_support | 1 | |
| 1442 | 交付 | 完成工业大数据分析交付 | direct_support | 1 | |
| 1443 | 交付 | 完成云端迁移项目交付 | direct_support | 1 | |
| 1444 | 交付 | 成功交付全面预算管理等重大项目 | direct_support | 1 | |
| 1445 | 交付 | 完成全面预算管理交付 | direct_support | 1 | |
| 1446 | 交付 | 数据治理专项高质量交付 | direct_support | 1 | |
| 1447 | 项目管理方法论 | 证书：信息系统项目管理师 | direct_support | 1 | |
| 1448 | 交付 | 后端架构升级高质量交付 | direct_support | 1 | |
| 1449 | 交付 | 方案设计与落地交付 | direct_support | 1 | |
| 1450 | pmp | 证书：hr管理师、pmp | direct_support | 1 | |
| 1451 | 跨部门协调与团队管理行为能力突出 | 跨部门沟通顺畅 | equivalent | 1 | |
| 1452 | 持续学习 | 主动学习 | direct_support | 1 | |
| 1453 | 执行推进可靠 | 主动承担责任 | direct_support | 1 | |
| 1454 | 执行推进可靠 | 零缺陷交付记录 | direct_support | 1 | |
| 1455 | 执行推进可靠 | 问题闭环改进 | direct_support | 1 | |
| 1456 | 学习敏捷 | 学习速度快，快速掌握新调度框架 | direct_support | 1 | |
| 1457 | 执行推进可靠 | 完成交付，当年绩效评定为a | direct_support | 1 | |
| 1458 | 学习敏捷 | 学习速度快，钻研新技术栈 | direct_support | 1 | |
| 1459 | 执行推进可靠 | 推进流程数字化落地 | direct_support | 1 | |
| 1460 | 绩效管理 | 培训：绩效管理实务（未开始） | direct_support | 1 | |
| 1461 | 薪酬福利与劳动关系管理 | 参与薪酬体系改革 | direct_support | 1 | |
| 1462 | 薪酬福利与劳动关系管理 | 岗位：薪酬福利专员 | direct_support | 1 | |
| 1463 | 招聘配置 | 岗位：招聘主管 | direct_support | 1 | |
| 1464 | 招聘配置 | 招聘主管 | direct_support | 1 | |
| 1465 | 培训开发 | 培训经理 | direct_support | 1 | |
| 1466 | 薪酬福利与劳动关系管理 | 薪酬福利专员 | direct_support | 1 | |
| 1467 | 薪酬福利与劳动关系管理 | 薪酬体系改革项目负责人 | direct_support | 1 | |
| 1468 | 主导hr领域项目全生命周期管理：范围界定 | 担任薪酬体系改革项目负责人，负责方案设计与落地交付 | equivalent | 1 | |
| 1469 | 跨部门协调：主动沟通 | 主导跨部门质量评审 | direct_support | 1 | |
| 1470 | 跨部门协调：主动沟通 | 跨部门沟通顺畅，2026年获得跨部门一致认可 | equivalent | 1 | |
| 1471 | 目标驱动达成 | 目标管理与okr（已完成）成绩89 | direct_support | 1 | |
| 1472 | 持续学习新方法新工具并迁移到hr场景 | 创新引入人力资源数字化方案 | direct_support | 1 | |
| 1473 | 持续学习新方法新工具并迁移到hr场景 | 参与人力资源数字化平台，负责资源协调 | direct_support | 1 | |
| 1474 | 持续学习新方法新工具并迁移到hr场景 | saphr/powerbi | direct_support | 1 | |
| 1475 | 持续学习新方法新工具并迁移到hr场景 | 创新引入薪酬体系设计方案 | direct_support | 1 | |
| 1476 | 绩效管理 | 目标管理与okr | direct_support | 1 | |
| 1477 | 书面表达 | 负责报告撰写 | direct_support | 1 | |
| 1478 | 沟通表达出色 | 沟通高效 | equivalent | 1 | |
| 1479 | 团队管理与执行推进可靠 | 承担过负责人角色 | direct_support | 1 | |
| 1480 | 团队管理与执行推进可靠 | 主动承担团队责任；态度端正 | direct_support | 1 | |
| 1481 | 团队管理与执行推进可靠 | 管理渐入佳境 | direct_support | 1 | |
| 1482 | 团队管理与执行推进可靠 | 领导力测评良好 | direct_support | 1 | |
| 1483 | 团队管理与执行推进可靠 | 团队建设与激励（已完成）成绩94 | direct_support | 1 | |
| 1484 | 成长型思维与领导潜质者优先 | 领导潜质 | direct_support | 1 | |
| 1485 | 团队管理与执行推进可靠 | 角色：项目负责人 | direct_support | 1 | |
| 1486 | 成长型思维与领导潜质者优先 | 管理渐入佳境 | direct_support | 1 | |
| 1487 | 成长型思维与领导潜质者优先 | 自然承担leader角色 | direct_support | 1 | |
| 1488 | 团队管理与执行推进可靠 | 承担负责人角色，具备基层管理能力；分内工作尽责到位 | direct_support | 1 | |
| 1489 | 团队管理与执行推进可靠 | 项目负责人，推进流程数字化落地 | direct_support | 1 | |
| 1490 | 绩效管理 | 培训：绩效管理实务（已完成）成绩76 | direct_support | 1 | |
| 1491 | 组织发展落地 | 参与组织架构优化项目，负责流程优化 | direct_support | 1 | |
| 1492 | 组织发展落地 | 参与组织架构优化项目，负责报告撰写，涉及组织诊断等技术应用 | direct_support | 1 | |
| 1493 | 组织发展落地 | 参与组织架构优化项目，负责报告撰写，涉及组织诊断 | direct_support | 1 | |
| 1494 | 组织发展落地 | 项目「组织架构优化项目」角色：核心成员 | direct_support | 1 | |
| 1495 | 组织发展落地 | 参与组织架构优化项目，负责交付管理 | direct_support | 1 | |
| 1496 | 绩效管理 | 2025年绩效合格c | direct_support | 1 | |
| 1497 | 组织发展落地 | 参与组织架构优化项目，负责资源协调 | direct_support | 1 | |
| 1498 | 绩效管理 | 培训：绩效管理实务（已完成）成绩86 | direct_support | 1 | |
| 1499 | 组织发展落地 | 参与组织架构优化项目，负责报告撰写 | direct_support | 1 | |
| 1500 | 绩效管理 | 培训：绩效管理实务（已完成）成绩88 | direct_support | 1 | |
| 1501 | 绩效管理 | 培训：绩效管理实务（已完成）成绩69 | direct_support | 1 | |
| 1502 | 绩效管理 | 2025年绩效良好b | direct_support | 1 | |
| 1503 | 适配表达风格 | 跨部门沟通协作 | direct_support | 1 | |
| 1504 | 适配表达风格 | 沟通风格亲和 | equivalent | 1 | |
| 1505 | 面向不同受众清晰表达与汇报 | 口头表达清晰，主导跨部门质量评审 | direct_support | 1 | |
| 1506 | 有效倾听 | 跨部门沟通顺畅 | equivalent | 1 | |
| 1507 | 持续学习 | 培训：精益生产管理（已完成） | direct_support | 1 | |
| 1508 | 持续学习 | 培训：合规管理体系（已完成） | direct_support | 1 | |
| 1509 | 持续学习 | 培训：职业健康安全（已完成） | direct_support | 1 | |
| 1510 | 持续学习 | 培训：企业文化建设（已完成） | direct_support | 1 | |
| 1511 | 持续学习 | 培训：商务谈判技巧（已完成） | direct_support | 1 | |
| 1512 | 持续学习 | 培训：创新思维与triz方法（已完成） | direct_support | 1 | |
| 1513 | 持续学习 | 培训：数字化转型战略（已完成） | direct_support | 1 | |
| 1514 | 持续学习 | 学习速度快，快速掌握新调度框架 | direct_support | 1 | |
| 1515 | 持续学习 | 学习速度快，钻研新技术栈 | direct_support | 1 | |
| 1516 | 微服务 | java微服务方案 | direct_support | 1 | |
| 1517 | spring | java/springboot/微服务 | direct_support | 1 | |
| 1518 | java及相关框架 | java微服务后端核心模块开发 | direct_support | 1 | |
| 1519 | 部署 | 工具：sap/oracle/java/ci/cd | direct_support | 1 | |
| 1520 | 部署 | 工具：ci/cd/sap/oracle/java | direct_support | 1 | |
| 1521 | 部署 | 工具：mysql/java/k8s/docker | direct_support | 1 | |
| 1522 | 团队管理经验或潜力 | 自然承担leader角色；承担过负责人角色 | direct_support | 1 | |
| 1523 | 团队管理经验或潜力 | 领导力发展工作坊（已完成） | direct_support | 1 | |
| 1524 | 团队管理经验或潜力 | 有带团队潜力；承担过负责人角色 | direct_support | 1 | |
| 1525 | 团队管理经验或潜力 | 管理渐入佳境；自然承担leader角色 | direct_support | 1 | |
| 1526 | 沟通表达清晰 | 跨部门沟通协作（已完成） | direct_support | 1 | |
| 1527 | 沟通表达清晰 | 跨部门沟通协作（已完成）成绩76 | direct_support | 1 | |
| 1528 | 团队管理经验或潜力 | 能激发团队士气；领导力测评良好 | direct_support | 1 | |
| 1529 | 沟通表达清晰 | 跨部门沟通协作（已完成）成绩84 | direct_support | 1 | |
| 1530 | 团队管理经验或潜力 | 能激发团队士气 | direct_support | 1 | |
| 1531 | 主动承担 | 自然承担leader角色 | direct_support | 1 | |
| 1532 | 主动承担 | 创新引入云计算方案 | direct_support | 1 | |
| 1533 | 自驱力突出 | 展现杰出专业能力和领导潜质 | direct_support | 1 | |
| 1534 | 主动承担 | 创新引入ci/cd流水线方案 | direct_support | 1 | |
| 1535 | 主动承担 | 主导产品迭代v3项目 | direct_support | 1 | |
| 1536 | 主动承担 | 担任核心角色 | direct_support | 1 | |
| 1537 | 主动承担 | 主导工业大数据分析项目 | direct_support | 1 | |
| 1538 | 主动承担 | 主导云端迁移项目 | direct_support | 1 | |
| 1539 | 微服务架构 | java微服务方案 | direct_support | 1 | |
| 1540 | 微服务架构 | java/springboot微服务架构 | equivalent | 1 | |
| 1541 | spring体系 | java/springboot/微服务 | direct_support | 1 | |
| 1542 | 前后端 | django/postgresql/react | direct_support | 1 | |
| 1543 | 前后端 | django/python/react | direct_support | 1 | |
| 1544 | 前后端 | 产品质量追溯系统，负责核心模块开发，涉及react | direct_support | 1 | |
| 1545 | 带领研发小组：组建团队 | 承担负责人角色，具备基层管理能力 | equivalent | 1 | |
| 1546 | 推动版本按期闭环交付 | 完成产品迭代v3等任务无重大失误 | direct_support | 1 | |
| 1547 | 推动版本按期闭环交付 | 主导产品迭代v3项目 | direct_support | 1 | |
| 1548 | 推动版本按期闭环交付 | 按时完成企业内控体系等任务 | direct_support | 1 | |
| 1549 | 推动版本按期闭环交付 | 较好完成企业内控体系交付 | direct_support | 1 | |
| 1550 | 推动版本按期闭环交付 | 成功交付薪酬体系改革等重大项目，获得跨部门一致认可 | direct_support | 1 | |
| 1551 | 推动版本按期闭环交付 | 成功交付流程再造工程等重大项目，获得跨部门一致认可 | direct_support | 1 | |
| 1552 | 自我设定目标 | 发挥关键作用 | direct_support | 1 | |

## 附：高频段代表性证据示例

1. **激励成员 ↔ 能激发团队士气**（JOB_B07/JZ0003）：专业功底深厚；代码质量好；团队中上水平；技术能力可信服；符合岗位要求；口头表达清晰；沟通直接高效；团队协作顺畅；沟通风格亲和；合作融洽；有带
2. **团队管理经验或潜力 ↔ 有带团队潜力**（JOB_B07/JZ0002）：专业技能扎实；专业能力强；独立交付OK；技术视野开阔；符合岗位要求；需更主动沟通；沟通直接高效；跨部门协调一般；布置任务清晰；合作融洽；有带
3. **交付 ↔ 负责交付管理**（JOB_B07/JZ0037）：项目「全面预算管理系统」角色：执行人；工具：SQL/Excel/用友NC/BI报表；参与全面预算管理系统，负责交付管理，涉及用友NC等技术应
4. **主动承担 ↔ 主动承担团队责任**（JOB_B10/JZ0002）：专业技能扎实；专业能力强；独立交付OK；技术视野开阔；符合岗位要求；需更主动沟通；沟通直接高效；跨部门协调一般；布置任务清晰；合作融洽；有带
5. **良好的沟通协调能力与质量意识 ↔ 质量意识强**（JOB_B01/JZ0001）：专业功底深厚；代码质量好；独立交付OK；技术视野开阔；技术匹配度高；跨部门沟通顺畅；协作态度好；团队协作顺畅；沟通风格亲和；合作融洽；需提升
6. **以骨干身份带动团队 ↔ 自然承担leader角色**（JOB_B06/JZ0001）：专业功底深厚；代码质量好；独立交付OK；技术视野开阔；技术匹配度高；跨部门沟通顺畅；协作态度好；团队协作顺畅；沟通风格亲和；合作融洽；需提升
7. **bi ↔ powerbi**（JOB_B07/JZ0026）：项目「人力资源数字化平台」角色：核心成员；工具：Power BI/OA/SAP HR/Excel；参与人力资源数字化平台，负责方案设计，涉及
8. **执行推进可靠 ↔ 非常靠谱**（JOB_B08/JZ0003）：专业功底深厚；代码质量好；团队中上水平；技术能力可信服；符合岗位要求；口头表达清晰；沟通直接高效；团队协作顺畅；沟通风格亲和；合作融洽；有带
9. **薪酬福利与劳动关系管理 ↔ 薪酬体系改革**（JOB_B08/JZ0026）：项目「薪酬体系改革」角色：协调人；工具：Excel/岗评工具/薪酬调研/合规审计；参与薪酬体系改革，负责资源协调，涉及Excel等技术应用。
10. **激励学员 ↔ 能激发团队士气**（JOB_B09/JZ0003）：专业功底深厚；代码质量好；团队中上水平；技术能力可信服；符合岗位要求；口头表达清晰；沟通直接高效；团队协作顺畅；沟通风格亲和；合作融洽；有带
11. **与跨职能团队沟通协作 ↔ 团队协作顺畅**（JOB_B06/JZ0004）：专业技能扎实；技术思路清晰；独立交付OK；技术视野开阔；技术匹配度高；口头表达清晰；乐于分享；团队协作顺畅；布置任务清晰；沟通反馈正面；管理
12. **良好的沟通表达与执行推进能力 ↔ 口头表达清晰**（JOB_B02/JZ0003）：专业功底深厚；代码质量好；团队中上水平；技术能力可信服；符合岗位要求；口头表达清晰；沟通直接高效；团队协作顺畅；沟通风格亲和；合作融洽；有带
13. **协调多部门资源 ↔ 负责资源协调**（JOB_B04/JZ0026）：参与薪酬体系改革，负责资源协调，涉及Excel等技术应用。；参与人力资源数字化平台，负责方案设计，涉及OA等技术应用。；参与全面预算管理系统
14. **面向不同受众清晰表达与汇报 ↔ 口头表达清晰**（JOB_B09/JZ0003）：专业功底深厚；代码质量好；团队中上水平；技术能力可信服；符合岗位要求；口头表达清晰；沟通直接高效；团队协作顺畅；沟通风格亲和；合作融洽；有带
15. **学习能力强 ↔ 学习速度快**（JOB_B02/JZ0002）：专业技能扎实；专业能力强；独立交付OK；技术视野开阔；符合岗位要求；需更主动沟通；沟通直接高效；跨部门协调一般；布置任务清晰；合作融洽；有带
16. **团队管理经验或潜力 ↔ 具备基层管理能力**（JOB_B07/JZ0004）：专业技能扎实；技术思路清晰；独立交付OK；技术视野开阔；技术匹配度高；口头表达清晰；乐于分享；团队协作顺畅；布置任务清晰；沟通反馈正面；管理
17. **团队管理与执行推进可靠 ↔ 具备基层管理能力**（JOB_B09/JZ0001）：专业功底深厚；代码质量好；独立交付OK；技术视野开阔；技术匹配度高；跨部门沟通顺畅；协作态度好；团队协作顺畅；沟通风格亲和；合作融洽；需提升
18. **学习敏捷性：快速学习新知识新技能 ↔ 学习速度快**（JOB_B06/JZ0002）：专业技能扎实；专业能力强；独立交付OK；技术视野开阔；符合岗位要求；需更主动沟通；沟通直接高效；跨部门协调一般；布置任务清晰；合作融洽；有带
19. **较强的流程梳理与交付管理能力 ↔ 独立交付ok**（JOB_B05/JZ0001）：专业功底深厚；代码质量好；独立交付OK；技术视野开阔；技术匹配度高；跨部门沟通顺畅；协作态度好；团队协作顺畅；沟通风格亲和；合作融洽；需提升
20. **团队管理经验或潜力 ↔ 承担过负责人角色**（JOB_B07/JZ0015）：专业功底深厚；技术思路清晰；团队中上水平；技术视野开阔；符合岗位要求；需更主动沟通；乐于分享；跨部门协调一般；布置任务清晰；沟通反馈正面；需
21. **学习敏捷 ↔ 学习速度快**（JOB_B08/JZ0002）：专业技能扎实；专业能力强；独立交付OK；技术视野开阔；符合岗位要求；需更主动沟通；沟通直接高效；跨部门协调一般；布置任务清晰；合作融洽；有带
22. **质量导向：标准合规 ↔ 质量意识强**（JOB_B06/JZ0001）：专业功底深厚；代码质量好；独立交付OK；技术视野开阔；技术匹配度高；跨部门沟通顺畅；协作态度好；团队协作顺畅；沟通风格亲和；合作融洽；需提升
23. **风险管理与交付验收 ↔ 负责交付管理**（JOB_B07/JZ0037）：项目「全面预算管理系统」角色：执行人；工具：SQL/Excel/用友NC/BI报表；参与全面预算管理系统，负责交付管理，涉及用友NC等技术应
24. **java及相关框架 ↔ java**（JOB_B10/JZ0004）：项目「ERP系统定制开发」角色：架构师；工具：SAP/Oracle/Java/CI/CD；参与ERP系统定制开发，负责性能优化，涉及Java
25. **良好的沟通表达与执行推进能力 ↔ 跨部门沟通顺畅**（JOB_B02/JZ0001）：专业功底深厚；代码质量好；独立交付OK；技术视野开阔；技术匹配度高；跨部门沟通顺畅；协作态度好；团队协作顺畅；沟通风格亲和；合作融洽；需提升
26. **主导方案设计与流程优化 ↔ 负责方案设计**（JOB_B04/JZ0026）：项目「企业内控体系建设」角色：协调人；工具：风险矩阵/审计软件/COSO/流程梳理；参与企业内控体系建设，负责方案设计，涉及审计软件等技术应
27. **较强的流程梳理与交付管理能力 ↔ 负责交付管理**（JOB_B05/JZ0027）：项目「薪酬体系改革」角色：项目负责人；工具：合规审计/岗评工具/薪酬调研/Excel；参与薪酬体系改革，负责交付管理，涉及合规审计等技术应用
28. **进度控制 ↔ 质量和进度符合预期**（JOB_B07/JZ0002）：2025年绩效良好B：2025年参与工业大数据分析项目，质量和进度符合预期。
29. **领导潜质发展通道 ↔ 领导潜质**（JOB_B09/JZ0003）：2026年绩效优秀A：2026年展现杰出专业能力和领导潜质，在产品迭代V3中发挥关键作用。
30. **主动承担 ↔ 主动承担责任**（JOB_B10/JZ0003）：专业功底深厚；代码质量好；团队中上水平；技术能力可信服；符合岗位要求；口头表达清晰；沟通直接高效；团队协作顺畅；沟通风格亲和；合作融洽；有带
31. **有领导潜质者优先 ↔ 展现杰出专业能力和领导潜质**（JOB_B06/JZ0030）：2025年绩效优秀A：2025年展现杰出专业能力和领导潜质，在薪酬体系改革中发挥关键作用。
32. **发挥影响力与担当 ↔ 主动承担团队责任**（JOB_B06/JZ0002）：专业技能扎实；专业能力强；独立交付OK；技术视野开阔；符合岗位要求；需更主动沟通；沟通直接高效；跨部门协调一般；布置任务清晰；合作融洽；有带
33. **团队管理经验或潜力 ↔ 自然承担leader角色**（JOB_B07/JZ0001）：专业功底深厚；代码质量好；独立交付OK；技术视野开阔；技术匹配度高；跨部门沟通顺畅；协作态度好；团队协作顺畅；沟通风格亲和；合作融洽；需提升
34. **团队管理经验或潜力 ↔ 领导力测评良好**（JOB_B07/JZ0005）：专业功底深厚；代码质量好；团队中上水平；技术视野开阔；符合岗位要求；口头表达清晰；乐于分享；跨部门协调一般；布置任务清晰；合作融洽；有带团队
35. **组建与管理研发小组：分配职责 ↔ 布置任务清晰**（JOB_B07/JZ0002）：专业技能扎实；专业能力强；独立交付OK；技术视野开阔；符合岗位要求；需更主动沟通；沟通直接高效；跨部门协调一般；布置任务清晰；合作融洽；有带
36. **带领项目团队：分配职责 ↔ 布置任务清晰**（JOB_B08/JZ0002）：专业技能扎实；专业能力强；独立交付OK；技术视野开阔；符合岗位要求；需更主动沟通；沟通直接高效；跨部门协调一般；布置任务清晰；合作融洽；有带
37. **成长型思维与领导潜质者优先 ↔ 领导力测评良好**（JOB_B09/JZ0005）：专业功底深厚；代码质量好；团队中上水平；技术视野开阔；符合岗位要求；口头表达清晰；乐于分享；跨部门协调一般；布置任务清晰；合作融洽；有带团队
38. **负责java后端服务与企业应用开发 ↔ java**（JOB_B10/JZ0004）：项目「ERP系统定制开发」角色：架构师；工具：SAP/Oracle/Java/CI/CD；参与ERP系统定制开发，负责性能优化，涉及Java
39. **嵌入式开发 ↔ 嵌入式**（JOB_B06/JZ0004）：项目「边缘计算网关开发」角色：核心开发；工具：MQTT/Linux/嵌入式/C++；参与边缘计算网关开发，负责代码审查，涉及Linux等技术
40. **良好的沟通表达与执行推进能力 ↔ 沟通直接高效**（JOB_B02/JZ0002）：专业技能扎实；专业能力强；独立交付OK；技术视野开阔；符合岗位要求；需更主动沟通；沟通直接高效；跨部门协调一般；布置任务清晰；合作融洽；有带