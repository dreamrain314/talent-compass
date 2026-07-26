"""模拟数据集生成脚本 - 100名员工 x 4类岗位

v1.1 修复记录（2026-07-22）：
  - [FIX] 360评价增加 year 字段，每年生成一套评价（3年×5维度×5角色=75条/人）
  - [FIX] 项目开始日期校验员工入职日期，不会出现入职前项目
  - [FIX] 评价者角色匹配：上级选年长/高职级，下属选年轻/低职级，HR选HR部门
  - [FIX] 绩效评语使用岗位序列匹配的技术栈/项目词汇
  - [FIX] 隐形高潜保证≥5人（C/B→B→A 或 B→B→A 或 B→A→A）
  - [FIX] training.completion_date 统一用 None/空字符串区分
"""
import csv, json, random, sys
from datetime import datetime, timedelta
from pathlib import Path

# 🔴 D2 单一来源：项目配置常量从 config 导入，禁止在此硬编码
_sys_path_added = str(Path(__file__).resolve().parent.parent)
if _sys_path_added not in sys.path:
    sys.path.insert(0, _sys_path_added)
from config import EVALUATOR_MIN_SAMPLE_SIZE, RAW_DATA_DIR  # noqa: E402 — 需要 sys.path 注入

random.seed(42)
# 🔴 D2 单一来源：用 config.RAW_DATA_DIR，禁硬编码 __file__/raw（原硬编码写 scripts/raw，
#    需手动 cp 同步 data/raw，违反单一来源；改后直接写 data/raw baseline）
RAW_DIR = RAW_DATA_DIR
RAW_DIR.mkdir(parents=True, exist_ok=True)

SN = ["王","李","张","刘","陈","杨","黄","赵","周","吴","徐","孙","马","朱","胡","郭","何","高","林","罗","郑","梁","谢","宋","唐","韩","曹","许","邓","冯","彭","曾","肖","田","董","潘","袁","蔡","蒋","余","于","杜","叶","程","苏","魏","吕","丁","任","沈","姚","卢","姜","崔","钟","谭","陆","汪","范","金","石","廖","贾","夏","韦","付","方","白","邹","孟","熊","秦","邱","江","尹","薛","闫","段","雷","侯","龙","史","陶","黎","贺","顾","毛","郝","龚","邵","万","钱","严","覃","武","戴","莫","孔","向","汤"]
GN = ["伟","芳","娜","秀英","敏","静","丽","强","磊","洋","勇","艳","杰","军","涛","明","华","慧","鑫","桂英","建军","建华","文","博","超","志强","秀兰","海燕","雪","浩","晨","宇","鹏","飞","嘉","睿","思源","一鸣","天宇","浩然","子涵","梓轩","雨桐","诗涵","若溪","晨曦","子轩","佳琪","欣然","乐天","政","锐","睿","恒","毅","峰","刚","松","柏","川","燕","红","梅","兰","菊","琴","霞","云","萍","玲"]

def p(x): return random.choice(x)
def pn(x,n): return random.sample(x,min(n,len(x)))
def gn(): return p(SN)+p(GN)
def gd(s,e):
    d=(datetime.strptime(e,"%Y-%m-%d")-datetime.strptime(s,"%Y-%m-%d")).days
    return (datetime.strptime(s,"%Y-%m-%d")+timedelta(days=random.randint(0,d))).strftime("%Y-%m-%d")
def wcsv(fn,rows,fds):
    fp=RAW_DIR/fn
    with open(fp,"w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fds); w.writeheader(); w.writerows(rows)
    print(f"OK {fn}: {len(rows)} rows")
def wjson(fn,data):
    fp=RAW_DIR/fn
    with open(fp,"w",encoding="utf-8-sig") as f: json.dump(data,f,ensure_ascii=False,indent=2)
    print(f"OK {fn}: {len(data)} records")

DT=["研发中心","信息技术部","智能制造事业部","软件工程部"]
DM=["人力资源部","财务管理部","行政办公室","战略发展部","审计部"]
DK=["市场部","销售部","客户服务部","品牌管理部"]
DI=["创新业务部","数字化转型办公室","新产业研究中心","投资发展部"]
PT=["软件工程师","硬件工程师","系统架构师","测试工程师","算法工程师","嵌入式开发工程师","FPGA工程师","结构设计工程师","工艺工程师","质量工程师"]
PM=["人力资源主管","财务经理","行政主管","战略规划师","审计专员","培训经理","薪酬福利专员","绩效经理","招聘主管","法务专员"]
PK=["市场总监","区域销售经理","客户经理","品牌策划师","渠道经理","市场分析师","新媒体运营","公共关系专员","产品经理","商务拓展"]
PI=["创新项目经理","数字化转型顾问","新业务孵化经理","产业研究员","投资分析师","商业策划师","技术转移专员","孵化器运营","战略合作经理","创新实验室研究员"]
MT=["计算机科学与技术","软件工程","电子信息工程","自动化","通信工程","机械设计制造及其自动化","测控技术与仪器","电气工程及其自动化","微电子科学与工程","人工智能"]
MM=["人力资源管理","工商管理","财务管理","会计学","行政管理","劳动与社会保障","心理学","法学","经济学","公共管理"]
MK=["市场营销","国际经济与贸易","广告学","新闻传播","电子商务","工商管理","商务英语","物流管理","统计学","金融学"]
MI=["创新管理","技术经济及管理","金融工程","数据科学","工业设计","信息管理与信息系统","生物医学工程","新能源科学与工程","材料科学与工程","环境工程"]

# ── 岗位序列感知的技术栈和项目词汇 ──
SEQ_TECHS = {
    "技术研发类": ["Java微服务","Python数据分析","AI算法","云计算","嵌入式开发","C++系统编程","Docker容器化","K8s编排","分布式架构","CI/CD流水线"],
    "管理职能类": ["流程优化","风险管控","合规审计","财务建模","人力资源数字化","组织诊断","薪酬体系设计","绩效管理"],
    "市场业务类": ["品牌策略","数字营销","市场洞察","客户关系管理","竞品分析","渠道建设","GTM策略","新媒体运营"],
    "新业务创新型": ["商业模型设计","技术评估","可行性分析","产业研究","投资建模","政策分析","MVP验证","创新方法论"],
}
SEQ_PROJECTS = {
    "技术研发类": ["智慧园区平台","ERP核心升级","工业大数据分析","云端迁移项目","安全合规加固","产品迭代V3","物联网平台","AI中台建设"],
    "管理职能类": ["全面预算管理","组织架构优化","薪酬体系改革","企业内控体系","合规管理提升","人才盘点项目","流程再造工程"],
    "市场业务类": ["品牌战略升级","海外市场拓展","数字化营销转型","大客户开发专项","新产品上市推广","全渠道整合","私域流量建设"],
    "新业务创新型": ["低空经济研究","新能源技术评估","数字化转型咨询","AI+新业务孵化","产业孵化器运营","碳中和路径研究"],
}


# ── 岗位序列感知的资质证书池 ──
# H1Filter 数据来源：certificates 字段用 ";" 分隔，无证书记 "无"。
# 设计依据（开题报告/五层匹配评分体系细化方案_2026-07-24.md §3.1）：
# H1 通过"证书标准名称映射表"精确匹配，故证书名称须用规范全称。
# PMP 刻意放入全部 4 个序列池 —— 它是跨序列通用项目管理证书，贴近真实。
SEQ_CERTS = {
    "技术研发类": ["系统架构设计师", "信息系统项目管理师", "软件设计师", "网络工程师", "PMP"],
    "管理职能类": ["CPA", "中级会计师", "高级会计师", "税务师", "HR管理师", "PMP"],
    "市场业务类": ["PMP", "营销师", "数据分析师", "商务英语"],
    "新业务创新型": ["CFA", "投资顾问", "PMP", "产业规划师"],
}

# 独立 RNG —— certificates 生成不得污染主 random 状态。
# 主链路（gen_perf/gen_proj/gen_train/gen_360）已有 seed=42 baseline 输出，
# 在 gen_emps 循环中插入 random 调用会推进全局 state → 改变后续所有字段值，
# 破坏 baseline 可重复性（C7：数据生成含跨字段断言，baseline 必须可复现）。
_CERT_RNG = random.Random(2026)


def _gen_certificates(seq: str, level_num: int) -> str:
    """生成员工资质证书字段。

    权重设计（D4 列假阳性 —— 以下合法分布必须能被生成到）：
    - 约 55% 员工无证书 → 覆盖 H1 required 不满足→直接排除 的测试场景
    - 约 30% 持 1 个证书 + 约 15% 持 2 个 → 覆盖 H1 preferred 满足→加分 场景
    - 高职级（level>=6）有证书概率上浮 15% → 贴近真实（资深者多持证），
      但保留 ≥30% 无证书下限，避免"高职级必有证"的伪强相关
    - 证书全部取自 SEQ_CERTS[seq]，保证岗位序列一致性（D2 跨表一致）
    - 使用独立 _CERT_RNG，不污染主 random 链路（baseline 可重复）

    Args:
        seq: 岗位序列名（如"技术研发类"）
        level_num: 职级数字（current_level 去 P 后的 int）

    Returns:
        ";" 分隔的证书字符串；无证书返回 "无"。
    """
    pool = SEQ_CERTS.get(seq, SEQ_CERTS["技术研发类"])
    no_p = 0.55 - (0.15 if level_num >= 6 else 0.0)
    no_p = max(0.30, no_p)  # 即使高职级也保留 30% 无证书下限

    if _CERT_RNG.random() < no_p:
        return "无"
    n = 2 if _CERT_RNG.random() < 0.20 else 1  # 有证者中约 20% 持 2 个
    certs = _CERT_RNG.sample(pool, min(n, len(pool)))
    return ";".join(certs)


def gen_emps():
    rows=[]
    cfgs=[("技术研发类",DT,PT,MT,(25,40)),("管理职能类",DM,PM,MM,(35,55)),("市场业务类",DK,PK,MK,(28,45)),("新业务创新型",DI,PI,MI,(28,48))]
    pp=["中共党员"]*30+["共青团员"]*20+["群众"]*48+["民主党派"]*2; random.shuffle(pp)
    ep=["博士"]*5+["硕士"]*20+["本科"]*55+["大专"]*20; random.shuffle(ep)
    for si,(sq,de,po,ma,ar) in enumerate(cfgs):
        for i in range(25):
            idx=si*25+i; eid=f"JZ{idx+1:04d}"; age=random.randint(*ar)
            mlv=max(1,(age-20)//5); Mlv=min(9,(age-20)//3+2)
            lv=min(9,max(1,int(random.gauss((mlv+Mlv)/2,1.5)))); lv=max(mlv,min(Mlv,lv))
            yos_raw = max(0, age - 22 - random.randint(0, 5))
            jitter_days = random.randint(0, 180)
            hd = datetime(2026, 7, 1) - timedelta(days=yos_raw * 365 + jitter_days)
            actual_yos = (datetime(2026, 7, 1) - hd).days // 365
            rows.append(dict(employee_id=eid, name=gn(), age=age, gender=p(["男", "女"]),
                         political_status=pp[idx], education=ep[idx],
                         major=p(ma), department=p(de), job_sequence=sq,
                         current_position=p(po), current_level=f"P{lv}",
                         hire_date=hd.strftime("%Y-%m-%d"),
                         years_of_service=actual_yos,
                         certificates=_gen_certificates(sq, lv)))
    return rows


# ── 岗位序列感知的绩效评语模板 ──
def _make_perf_templates():
    """为每个岗位序列生成专用评语模板"""
    templates = {}
    for seq in SEQ_TECHS:
        PA_seq = [
            f"{{y}}年度表现卓越，主导{{pr}}项目攻克{{tk}}技术难题，超额完成目标。",
            f"{{y}}年展现杰出专业能力和领导潜质，在{{pr}}中发挥关键作用。",
            f"{{y}}年度绩效突出，创新引入{{tk}}方案，效率提升超30%。",
            f"{{y}}年成功交付{{pr}}等重大项目，获得跨部门一致认可。",
            f"{{y}}年在{{pr}}中担任核心角色，产出质量远超预期。",
        ]
        PB_seq = [
            f"{{y}}年整体良好，按时完成{{pr}}等任务，认真负责。",
            f"{{y}}年参与{{pr}}项目，质量和进度符合预期。",
            f"{{y}}年工作态度端正，较好完成{{pr}}交付。",
            f"{{y}}年表现稳定，在{{pr}}中配合到位。",
            f"{{y}}年完成{{pr}}等任务无重大失误，日常表现踏实。",
        ]
        PC_seq = [
            f"{{y}}年绩效有改进空间，{{pr}}中部分节点延迟。",
            f"{{y}}年在{{tk}}方面存在能力差距，需针对性提升。",
            f"{{y}}年交付质量不够稳定，{{pr}}出现沟通不畅和返工。",
        ]
        PD_seq = [
            f"{{y}}年度不达标，{{pr}}严重延期且质量问题频发，需PIP。",
        ]
        templates[seq] = {"A": PA_seq, "B": PB_seq, "C": PC_seq, "D": PD_seq}
    return templates

PERF_TEMPLATES = _make_perf_templates()


def gen_perf(emps):
    rows=[]
    # 隐形高潜：强制生成 ≥5 人（C→B→A 或 B→B→A 或 B→A→A）
    hp_pool = [e for e in emps if 3 <= int(e["current_level"][1:]) <= 5]
    hp_paths = [
        {"2024": "C", "2025": "B", "2026": "A"},
        {"2024": "B", "2025": "B", "2026": "A"},
        {"2024": "B", "2025": "A", "2026": "A"},
        {"2024": "C", "2025": "B", "2026": "B"},
    ]
    hp = set()
    shuffled_pool = random.sample(hp_pool, len(hp_pool))
    for e in shuffled_pool:
        if len(hp) >= 8:
            break
        hp.add(e["employee_id"])
    if len(hp) < 5:
        hp = set(e["employee_id"] for e in hp_pool[:8])

    for e in emps:
        ih = e["employee_id"] in hp
        seq = e["job_sequence"]
        templates = PERF_TEMPLATES.get(seq, PERF_TEMPLATES["技术研发类"])
        techs = SEQ_TECHS.get(seq, SEQ_TECHS["技术研发类"])
        projects = SEQ_PROJECTS.get(seq, SEQ_PROJECTS["技术研发类"])

        # 🔴 修复 Bug 3：只生成入职后年份的绩效数据，防止入职前绩效
        hire_year = datetime.strptime(e["hire_date"], "%Y-%m-%d").year
        applicable_years = [y for y in [2024, 2025, 2026] if y >= hire_year]

        path = None
        if ih and applicable_years:
            path = p(hp_paths)
        for y in applicable_years:
            if ih:
                g = path[str(y)]
            else:
                w = {"A": 15, "B": 50, "C": 30, "D": 5}
                if seq == "管理职能类" and e["age"] > 45:
                    w = {"A": 20, "B": 55, "C": 22, "D": 3}
                g = random.choices(list(w), weights=list(w.values()))[0]
            t = p(templates[g]).format(y=y, tk=p(techs), pr=p(projects))
            rows.append(dict(employee_id=e["employee_id"], year=y,
                           performance_grade=g, performance_comment=t))
    print(f"[数据] 隐形高潜: {len(hp)} 人 ({sorted(hp)[:5]}...)")
    return rows


SPS = {
    "技术研发类": [
        {"n": "智能制造MES系统升级", "t": ["Java", "Spring Cloud", "MySQL", "Docker", "K8s"]},
        {"n": "工业大数据分析平台", "t": ["Python", "Spark", "Hadoop", "Tableau", "Airflow"]},
        {"n": "智能仓储WMS系统", "t": ["C#", ".NET Core", "SQL Server", "Redis"]},
        {"n": "边缘计算网关开发", "t": ["C++", "Linux", "MQTT", "嵌入式"]},
        {"n": "数字孪生可视化平台", "t": ["Three.js", "Node.js", "MongoDB", "Unity"]},
        {"n": "产品质量追溯系统", "t": ["Python", "Django", "PostgreSQL", "React"]},
        {"n": "工业IoT管理平台", "t": ["Go", "gRPC", "InfluxDB", "Grafana"]},
        {"n": "AI视觉检测系统", "t": ["Python", "PyTorch", "OpenCV", "FastAPI"]},
        {"n": "ERP系统定制开发", "t": ["Java", "SAP", "Oracle", "CI/CD"]},
        {"n": "工业机器人控制", "t": ["C++", "ROS", "EtherCAT", "PLC"]},
    ],
    "管理职能类": [
        {"n": "人力资源数字化平台", "t": ["SAP HR", "Excel", "Power BI", "OA"]},
        {"n": "全面预算管理系统", "t": ["用友NC", "Excel", "SQL", "BI报表"]},
        {"n": "组织架构优化项目", "t": ["组织诊断", "人才测评", "360评估", "战略地图"]},
        {"n": "薪酬体系改革", "t": ["薪酬调研", "岗评工具", "Excel", "合规审计"]},
        {"n": "企业内控体系建设", "t": ["COSO", "风险矩阵", "流程梳理", "审计软件"]},
    ],
    "市场业务类": [
        {"n": "品牌战略升级", "t": ["市场调研", "品牌定位", "媒体投放", "数据分析"]},
        {"n": "海外市场拓展", "t": ["市场分析", "渠道建设", "跨境物流", "本地化"]},
        {"n": "数字化营销转型", "t": ["SEO/SEM", "CRM", "数据分析", "内容营销"]},
        {"n": "大客户开发专项", "t": ["客户调研", "方案定制", "商务谈判", "合同管理"]},
        {"n": "新产品上市推广", "t": ["竞品分析", "定价策略", "渠道推广", "KOL"]},
    ],
    "新业务创新型": [
        {"n": "低空经济产业研究", "t": ["行业调研", "可行性分析", "政策研究", "商业模型"]},
        {"n": "新能源技术评估", "t": ["技术评估", "市场预测", "投资分析", "专家访谈"]},
        {"n": "数字化转型咨询", "t": ["咨询方法论", "流程再造", "数字化", "变革管理"]},
        {"n": "新业务孵化AI+", "t": ["AI技术", "商业模式画布", "MVP", "融资对接"]},
        {"n": "产业孵化器运营", "t": ["孵化器管理", "项目评估", "资源对接", "创业辅导"]},
    ],
}
RS = {
    "技术研发类": ["技术负责人", "核心开发", "架构师", "项目成员"],
    "管理职能类": ["项目负责人", "核心成员", "协调人", "执行人"],
    "市场业务类": ["项目负责人", "市场负责人", "执行人", "协调人"],
    "新业务创新型": ["项目负责人", "研究员", "投资分析师", "孵化负责人"],
}
SEQ_TASKS = {
    "技术研发类": ["核心模块开发", "架构设计", "性能优化", "代码审查", "技术攻关"],
    "管理职能类": ["方案设计", "资源协调", "流程优化", "报告撰写", "交付管理"],
    "市场业务类": ["市场分析", "客户调研", "方案定制", "渠道拓展", "项目管理"],
    "新业务创新型": ["可行性研究", "商业分析", "资源对接", "项目孵化", "技术评估"],
}


def gen_proj(emps):
    ap = []
    for e in emps:
        hd = datetime.strptime(e["hire_date"], "%Y-%m-%d")
        sq = e["job_sequence"]
        pp = SPS.get(sq, SPS["技术研发类"])
        rp = RS.get(sq, ["项目成员"])
        tasks = SEQ_TASKS.get(sq, ["项目执行"])

        for pr in random.sample(pp, min(random.randint(1, 4), len(pp))):
            # 🔴 修复：项目开始日期必须在入职日期之后（至少 30 天）
            earliest_start = max(
                datetime(2022, 1, 1),
                hd + timedelta(days=30),
            )
            earliest_str = earliest_start.strftime("%Y-%m-%d")
            s = gd(earliest_str, "2026-06-01")
            ed = min(
                datetime.strptime(s, "%Y-%m-%d") + timedelta(days=random.randint(90, 540)),
                datetime(2026, 7, 1),
            ).strftime("%Y-%m-%d")

            ap.append(dict(
                employee_id=e["employee_id"],
                project_name=pr["n"],
                role=p(rp),
                start_date=s,
                end_date=ed,
                description=f"参与{pr['n']}，负责{p(tasks)}，涉及{p(pr['t'])}等技术应用。",
                team_size=random.randint(3, 15),
                tools_used=pn(pr["t"], min(4, len(pr["t"]))),
            ))
    return ap


COURSES = [
    "Python数据分析实战", "项目管理PMP认证", "领导力发展工作坊", "安全生产标准化培训",
    "质量管理体系ISO9001", "数字化转型战略", "智能制造技术前沿", "商务谈判技巧",
    "财务分析与管理会计", "创新思维与TRIZ方法", "人工智能基础与应用", "跨部门沟通协作",
    "绩效管理实务", "企业文化建设", "新产品开发流程", "供应链管理优化",
    "法律风险防控", "精益生产管理", "六西格玛绿带", "数据可视化与报表",
    "云计算与大数据基础", "客户关系管理", "团队建设与激励", "目标管理与OKR",
    "商业计划书撰写", "合规管理体系", "职业健康安全", "职场英语提升",
]


def gen_train(emps):
    """生成培训记录。

    completion_date 语义：
      - "已完成": 具体日期（2023-01-01 ~ 2026-06-30）
      - "进行中": 空字符串（培训尚未结束，无完成日期）
      - "未开始": 空字符串（尚未启动，score=0）

    注意：下游 Agent 在判断"培训完成率"时，需同时检查 status 和
    completion_date——仅统计 status="已完成" 且有日期的记录。
    """
    rows = []
    for e in emps:
        for c in random.sample(COURSES, random.randint(2, 6)):
            st = random.choices(["已完成", "进行中", "未开始"], weights=[60, 25, 15])[0]
            sc = random.randint(60, 100) if st == "已完成" else (
                random.randint(30, 90) if st == "进行中" else 0)
            cd = gd("2023-01-01", "2026-06-30") if st == "已完成" else ""
            rows.append(dict(
                employee_id=e["employee_id"],
                course_name=c,
                completion_date=cd,
                status=st,
                score=sc,
            ))
    return rows


DIMS = ["专业能力", "沟通协作", "领导力", "责任心", "学习能力"]
DS = {
    "专业能力": {
        "上级": [1, 2, 4, 5, 5, 4, 4, 5, 3, 4, 5, 4, 5, 5, 2],
        "同事": [2, 3, 4, 5, 4, 3, 4, 5, 4, 4, 3, 4, 5, 1],
        "下属": [1, 4, 5, 4, 3, 5, 4, 4, 3, 5, 4, 2],
        "自评": [2, 4, 5, 5, 4, 3, 5, 4, 4, 5, 3, 1],
        "HR": [1, 4, 4, 5, 3, 4, 4, 5, 4, 4, 3, 2],
    },
    "沟通协作": {
        "上级": [2, 3, 4, 4, 5, 3, 4, 5, 4, 3, 4, 5, 4, 1],
        "同事": [1, 3, 4, 5, 4, 3, 4, 5, 4, 3, 4, 5, 2],
        "下属": [2, 4, 5, 4, 3, 4, 5, 4, 3, 4, 5, 1],
        "自评": [1, 4, 5, 4, 3, 4, 5, 4, 3, 4, 5, 2],
        "HR": [2, 3, 4, 5, 4, 3, 4, 5, 4, 3, 4, 1],
    },
    "领导力": {
        "上级": [1, 3, 4, 5, 3, 4, 5, 4, 3, 4, 5, 3, 4, 2],
        "同事": [2, 3, 4, 4, 5, 3, 4, 5, 3, 4, 4, 3, 1],
        "下属": [1, 3, 4, 5, 4, 3, 5, 4, 3, 4, 5, 2],
        "自评": [2, 3, 4, 5, 4, 3, 5, 4, 3, 4, 5, 1],
        "HR": [1, 3, 4, 4, 3, 4, 5, 4, 3, 4, 5, 2],
    },
    "责任心": {
        "上级": [1, 4, 5, 4, 5, 4, 3, 5, 4, 5, 4, 5, 4, 2],
        "同事": [2, 3, 4, 5, 4, 3, 4, 5, 4, 3, 4, 5, 1],
        "下属": [1, 4, 5, 4, 3, 5, 4, 4, 3, 5, 4, 2],
        "自评": [2, 4, 5, 4, 5, 4, 5, 4, 3, 5, 4, 1],
        "HR": [1, 4, 4, 5, 4, 3, 4, 5, 4, 3, 4, 2],
    },
    "学习能力": {
        "上级": [1, 3, 4, 5, 4, 3, 4, 5, 4, 3, 4, 5, 3, 2],
        "同事": [2, 3, 4, 5, 4, 3, 4, 5, 3, 4, 5, 3, 1],
        "下属": [1, 4, 5, 4, 3, 5, 4, 3, 4, 5, 3, 2],
        "自评": [2, 4, 5, 4, 3, 5, 4, 3, 4, 5, 4, 1],
        "HR": [1, 3, 4, 5, 4, 3, 4, 5, 3, 4, 5, 2],
    },
}
DC = {
    "专业能力": {
        "上级": ["专业技能扎实", "专业功底深厚", "技术有提升空间"],
        "同事": ["专业能力强", "技术思路清晰", "代码质量好"],
        "下属": ["技术视野开阔", "技术能力可信服"],
        "自评": ["团队中上水平", "独立交付OK"],
        "HR": ["符合岗位要求", "技术匹配度高"],
    },
    "沟通协作": {
        "上级": ["跨部门沟通顺畅", "口头表达清晰", "需更主动沟通"],
        "同事": ["协作态度好", "沟通直接高效", "乐于分享"],
        "下属": ["沟通风格亲和", "布置任务清晰"],
        "自评": ["团队协作顺畅", "跨部门协调一般"],
        "HR": ["沟通反馈正面", "合作融洽"],
    },
    "领导力": {
        "上级": ["有带团队潜力", "管理渐入佳境", "需提升战略思维"],
        "同事": ["有主见能推动决策", "自然承担leader角色"],
        "下属": ["给予充分信任", "能激发团队士气"],
        "自评": ["管理经验需积累", "承担过负责人角色"],
        "HR": ["具备基层管理能力", "领导力测评良好"],
    },
    "责任心": {
        "上级": ["高度负责", "主动承担责任", "关键时刻能兜底"],
        "同事": ["非常靠谱", "质量意识强"],
        "下属": ["主动承担团队责任", "为下属争取资源"],
        "自评": ["分内工作尽责到位", "结果导向"],
        "HR": ["态度端正", "责任维度得分高"],
    },
    "学习能力": {
        "上级": ["学习速度快", "主动学习前沿"],
        "同事": ["新技术上手快", "快速查资料解决"],
        "下属": ["分享行业新知", "带领探索新技术"],
        "自评": ["保持持续学习", "跨领域需更系统"],
        "HR": ["培训学分完成率好", "主动学习意识强"],
    },
}


def _pick_evaluator_for_role(emps, target_emp, role):
    """🔴 修复：按角色逻辑匹配评价者"""
    eid = target_emp["employee_id"]
    level_num = int(target_emp["current_level"][1:])
    age = target_emp["age"]
    sq = target_emp["job_sequence"]

    others = [e for e in emps if e["employee_id"] != eid]

    if role == "自评":
        return eid
    elif role == "上级":
        candidates = [e for e in others
                      if int(e["current_level"][1:]) > level_num and e["age"] > age]
        if not candidates:
            candidates = [e for e in others
                          if int(e["current_level"][1:]) >= level_num and e["age"] > age]
        if not candidates:
            candidates = others
        return p(candidates)["employee_id"]
    elif role == "下属":
        candidates = [e for e in others
                      if int(e["current_level"][1:]) < level_num and e["age"] < age]
        if not candidates:
            candidates = [e for e in others
                          if int(e["current_level"][1:]) <= level_num and e["age"] < age]
        if not candidates:
            candidates = others
        return p(candidates)["employee_id"]
    elif role == "同事":
        candidates = [e for e in others if e["department"] == target_emp["department"]]
        if not candidates:
            candidates = [e for e in others if e["job_sequence"] == sq]
        if not candidates:
            candidates = others
        return p(candidates)["employee_id"]
    elif role == "HR":
        hr_depts = ["人力资源部", "行政办公室"]
        candidates = [e for e in others if e["department"] in hr_depts]
        if not candidates:
            candidates = others
        return p(candidates)["employee_id"]
    return p(others)["employee_id"]


def gen_360(emps):
    rows = []
    eids = [e["employee_id"] for e in emps]
    anom = set(random.sample(eids, 4))
    ext = set(sorted(anom)[:2])
    dev = anom - ext

    for e in emps:
        eid = e["employee_id"]
        rn = ["上级", "同事", "自评", "下属", "HR"]

        # 为每个角色预选评价者（角色匹配），跨年份保持一致
        role_evaluators = {}
        for role in rn:
            role_evaluators[role] = _pick_evaluator_for_role(emps, e, role)

        # 🔴 修复：3 年数据，每年一套完整评价
        for year in [2024, 2025, 2026]:
            for dim in DIMS:
                for role in rn:
                    ev = role_evaluators[role]
                    sc = p(DS[dim][role])

                    # 异常评价者逻辑（跳过自评）
                    if role == "自评":
                        pass
                    elif ev in ext:
                        sc = 5
                    elif ev in dev:
                        if sc >= 4:
                            sc = min(5, sc + random.randint(1, 2))
                        elif sc <= 2:
                            sc = max(1, sc - random.randint(1, 2))

                    sc = max(1, min(5, sc))
                    rows.append(dict(
                        employee_id=eid,
                        evaluator_id=ev,
                        evaluator_role=role,
                        dimension=dim,
                        score=sc,
                        comment=p(DC[dim][role]),
                        year=year,
                    ))

    # ── 校验 ──
    ext_only5 = all(row["score"] == 5 for row in rows
                    if row["evaluator_id"] in ext and row["evaluator_role"] != "自评")
    dev_scores = [row["score"] for row in rows
                  if row["evaluator_id"] in dev and row["evaluator_role"] != "自评"]
    dev_biased = (len([s for s in dev_scores if s in (1, 2, 4, 5)]) >
                  len(dev_scores) * 0.3) if dev_scores else False
    print(f"[校验360] 极端({len(ext)}人):{'全5分' if ext_only5 else '有非5分!'} | "
          f"偏差({len(dev)}人): 非3分占比="
          f"{len([s for s in dev_scores if s in (1,2,4,5)])}/{len(dev_scores)}"
          + (" (偏差生效)" if dev_biased else " (偏差可能未生效!)"))

    # 验证每年每人有 5×5=25 条记录
    year_counts = {}
    for row in rows:
        key = (row["employee_id"], row["year"])
        year_counts[key] = year_counts.get(key, 0) + 1
    missing = [(eid, y) for (eid, y), c in year_counts.items() if c != 25]
    if missing:
        print(f"[校验360] ⚠ 记录数≠25的员工-年: {len(missing)}")

    return rows, ext, dev


def generate_all():
    print("=" * 50)
    print("Talent Compass Mock Data Generator v1.1")
    print(f"Seed: 42 | {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 50)

    print("\n[1/5] employees...")
    emps = gen_emps()
    wcsv("employees.csv", emps, [
        "employee_id", "name", "age", "gender", "political_status",
        "education", "major", "department", "job_sequence",
        "current_position", "current_level", "hire_date", "years_of_service",
        "certificates",
    ])

    print("\n[2/5] performance...")
    perf = gen_perf(emps)
    wcsv("performance.csv", perf, [
        "employee_id", "year", "performance_grade", "performance_comment",
    ])

    print("\n[3/5] projects...")
    proj = gen_proj(emps)
    wjson("projects.json", proj)

    print("\n[4/5] training...")
    tr = gen_train(emps)
    wcsv("training.csv", tr, [
        "employee_id", "course_name", "completion_date", "status", "score",
    ])

    print("\n[5/5] evaluation_360...")
    ev, ext_eval, dev_eval = gen_360(emps)
    wcsv("evaluation_360.csv", ev, [
        "employee_id", "evaluator_id", "evaluator_role",
        "dimension", "score", "comment", "year",
    ])

    print(f"\n{'=' * 50}")
    print(f"Done! emps={len(emps)} perf={len(perf)} proj={len(proj)} "
          f"train={len(tr)} eval360={len(ev)}")
    print("注意: eval360 现已包含 year 字段（2024/2025/2026 各一套完整评价）")
    print(f"      perf 行数可能 <300（入职晚的员工无早年绩效记录）")
    print("=" * 50)

    # ── 一致性校验 ──
    print("\n[校验] 字段一致性检查...")
    errors = []
    for e in emps:
        hd_date = datetime.strptime(e["hire_date"], "%Y-%m-%d")
        calc_yos = (datetime(2026, 7, 1) - hd_date).days // 365
        if abs(calc_yos - e["years_of_service"]) > 1:
            errors.append((e["employee_id"], e["years_of_service"], calc_yos))
    if errors:
        print(f"[FAIL] hire_date-yos consistency: {len(errors)} records mismatch")
        for eid, stored, calc in errors[:5]:
            print(f"   {eid}: stored={stored}, calculated={calc}")
    else:
        print("[OK] hire_date <-> years_of_service consistency check passed")

    # 项目日期校验
    proj_errors = 0
    for proj_item in proj:
        emp = next((e for e in emps if e["employee_id"] == proj_item["employee_id"]), None)
        if emp:
            hd = datetime.strptime(emp["hire_date"], "%Y-%m-%d")
            ps = datetime.strptime(proj_item["start_date"], "%Y-%m-%d")
            if ps < hd + timedelta(days=30):
                proj_errors += 1
    if proj_errors:
        print(f"[WARN] 项目开始日期在入职后30天内: {proj_errors} 条 (可能因入职时间较短)")
    else:
        print("[OK] 项目日期与入职日期一致性通过")

    # 360 年份覆盖校验
    year_coverage = set()
    for row in ev:
        year_coverage.add((row["employee_id"], row["year"]))
    missing_years = 100 * 3 - len(year_coverage)
    if missing_years > 0:
        print(f"[WARN] eval360 缺少 {missing_years} 员工-年组合")
    else:
        print("[OK] eval360: 100人 × 3年 = 300 员工-年全部覆盖")

    # 🔴 Bug 5 修复：验证异常评价者实际出现在评估数据中
    anom_in_data = set()
    for row in ev:
        rid = row["evaluator_id"]
        if rid in ext_eval or rid in dev_eval:
            anom_in_data.add(rid)
    missing_anom = (ext_eval | dev_eval) - anom_in_data
    if missing_anom:
        print(f"[WARN] 异常评价者 {len(missing_anom)}/4 未出现在评估数据中，正在强制注入...")
        # 强制注入：随机选择员工，将其"同事"评价者替换为缺失的异常评价者
        for anom_id in missing_anom:
            injected = 0
            for row in ev:
                if row["evaluator_role"] == "同事" and row["evaluator_id"] != anom_id and injected < 5:
                    row["evaluator_id"] = anom_id
                    # 重新应用异常逻辑
                    if anom_id in ext_eval:
                        row["score"] = 5
                    elif anom_id in dev_eval:
                        sc = row["score"]
                        if sc >= 4:
                            sc = min(5, sc + random.randint(1, 2))
                        elif sc <= 2:
                            sc = max(1, sc - random.randint(1, 2))
                        row["score"] = max(1, min(5, sc))
                    injected += 1
            print(f"  → 异常评价者 {anom_id} 已注入 {injected} 条记录")
    else:
        print(f"[OK] 异常评价者 4/4 全部出现在评估数据中")

    # 统计每个评价者的评估数据点数量（供 Agent① 域级异常检测参考）
    evaluator_counts = {}
    for row in ev:
        rid = row["evaluator_id"]
        evaluator_counts[rid] = evaluator_counts.get(rid, 0) + 1
    low_sample = {rid: c for rid, c in evaluator_counts.items() if c < EVALUATOR_MIN_SAMPLE_SIZE}
    if low_sample:
        print(f"[INFO] 评价者样本量 <15 的: {len(low_sample)} 人 "
              f"(域级异常检测时需跳过，标记 insufficient_data)")
    print(f"[INFO] 评价者样本量: min={min(evaluator_counts.values())}, "
          f"max={max(evaluator_counts.values())}, "
          f"median={sorted(evaluator_counts.values())[len(evaluator_counts)//2]}")

    # certificates 字段校验（H1Filter 数据来源）
    empty_certs = [e for e in emps
                   if not e.get("certificates") or e["certificates"] == ""]
    if empty_certs:
        print(f"[FAIL] certificates 空值: {len(empty_certs)} 人（应为 '无' 而非空）")
    else:
        with_certs = [e for e in emps if e["certificates"] != "无"]
        pct = len(with_certs) * 100 // len(emps)
        print(f"[OK] certificates: {len(with_certs)}/{len(emps)} 持证 ({pct}%)，"
              f"无空值")

        # 序列一致性：每个证书须在其员工岗位序列的证书池内
        seq_violations = []
        for e in emps:
            if e["certificates"] == "无":
                continue
            pool = set(SEQ_CERTS.get(e["job_sequence"], []))
            for c in e["certificates"].split(";"):
                if c not in pool:
                    seq_violations.append(
                        (e["employee_id"], c, e["job_sequence"]))
        if seq_violations:
            print(f"[WARN] 证书跨序列池: {len(seq_violations)} 条 "
                  f"(示例: {seq_violations[:3]})")
        else:
            print("[OK] certificates 全部在岗位序列池内（序列一致）")

        # 持证率分序列统计（H1Filter 测试需覆盖各序列）
        by_seq = {}
        for e in emps:
            sq = e["job_sequence"]
            by_seq.setdefault(sq, {"total": 0, "with": 0})
            by_seq[sq]["total"] += 1
            if e["certificates"] != "无":
                by_seq[sq]["with"] += 1
        for sq, st in by_seq.items():
            print(f"[INFO] {sq}: 持证 {st['with']}/{st['total']}")


if __name__ == "__main__":
    generate_all()
