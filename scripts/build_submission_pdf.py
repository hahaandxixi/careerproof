"""Build the competition technical-document candidate from verified project facts.

数据来源：2026-10-02 仓库实测（后端 pytest 770 通过/20 跳过、Ruff 通过；前端 tsc、102 项
Node 测试与生产构建通过）与 docs/DeepSeek统一路线与能力验收.md 能力矩阵。生成命令：
backend/.venv/Scripts/python.exe scripts/build_submission_pdf.py（依赖 reportlab，仅本地构建用）。
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "CareerProof-技术文档-提交候选稿.pdf"
pdfmetrics.registerFont(TTFont("SimHei", r"C:\Windows\Fonts\simhei.ttf"))

INK = colors.HexColor("#14243C")
BLUE = colors.HexColor("#1769AA")
SOFT = colors.HexColor("#EAF2F9")
GRAY = colors.HexColor("#526176")
styles = {
    "title": ParagraphStyle("title", fontName="SimHei", fontSize=28, leading=40,
                            textColor=INK, alignment=TA_LEFT, spaceAfter=18, wordWrap="CJK"),
    "subtitle": ParagraphStyle("subtitle", fontName="SimHei", fontSize=14, leading=23,
                               textColor=BLUE, spaceAfter=18, wordWrap="CJK"),
    "h1": ParagraphStyle("h1", fontName="SimHei", fontSize=17, leading=27,
                         textColor=INK, spaceBefore=10, spaceAfter=12, wordWrap="CJK"),
    "h2": ParagraphStyle("h2", fontName="SimHei", fontSize=11.5, leading=19,
                         textColor=BLUE, spaceBefore=8, spaceAfter=5, wordWrap="CJK"),
    "body": ParagraphStyle("body", fontName="SimHei", fontSize=9.2, leading=16,
                           textColor=INK, spaceAfter=7, wordWrap="CJK"),
    "small": ParagraphStyle("small", fontName="SimHei", fontSize=8, leading=13,
                            textColor=GRAY, spaceAfter=5, wordWrap="CJK"),
    "cell": ParagraphStyle("cell", fontName="SimHei", fontSize=8.2, leading=12.6,
                           textColor=INK, wordWrap="CJK"),
    "cellhead": ParagraphStyle("cellhead", fontName="SimHei", fontSize=8.2, leading=12.6,
                               textColor=BLUE, wordWrap="CJK"),
    "cover": ParagraphStyle("cover", fontName="SimHei", fontSize=10, leading=18,
                            textColor=GRAY, spaceAfter=7, wordWrap="CJK"),
    "covertitle": ParagraphStyle("covertitle", fontName="SimHei", fontSize=11, leading=20,
                                 textColor=INK, alignment=TA_CENTER, spaceAfter=4, wordWrap="CJK"),
    "disclaimer": ParagraphStyle("disclaimer", fontName="SimHei", fontSize=8.2, leading=14,
                                 textColor=GRAY, borderPadding=6, wordWrap="CJK"),
}


def p(text, style="body"):
    return Paragraph(text, styles[style])


def title(text):
    return [p(text, "h1"), HRFlowable(width="100%", thickness=1, color=BLUE), Spacer(1, 10)]


def table(rows, widths):
    data = [[p(str(value), "cellhead" if index == 0 else "cell") for value in row]
            for index, row in enumerate(rows)]
    result = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SOFT),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CEDAE6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return result


def page(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#D8E3ED"))
    canvas.line(21 * mm, height - 18 * mm, width - 21 * mm, height - 18 * mm)
    canvas.setFont("SimHei", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(21 * mm, 15 * mm, "CareerProof · 技术文档候选稿 v2 · 2026-10-02")
    canvas.drawRightString(width - 21 * mm, 15 * mm, str(doc.page))
    canvas.restoreState()


story = []

# ---------------- 封面 ----------------
story += [Spacer(1, 26 * mm), p("职证 CareerProof", "title"),
          p("证据链驱动的可信求职匹配与成长平台", "subtitle"),
          HRFlowable(width="100%", thickness=2, color=BLUE), Spacer(1, 12 * mm),
          p("全国高校 AI Web 开发挑战赛 · 技术文档候选稿 v2", "covertitle"),
          Spacer(1, 6 * mm),
          p("学校：广州软件学院", "cover"),
          p("参赛组别：B组", "cover"),
          p("团队：jz（报名编号 38419）　成员：江博、郑振南　指导教师：杨斌", "cover"),
          p("版本日期：2026 年 10 月 2 日（对应仓库 2026-09-17 起的 104 个真实提交）", "cover"),
          p("代码仓库：github.com/hahaandxixi/careerproof（比赛期间私有，按赛事规则向评审授权访问；赛后计划开源）", "cover"),
          Spacer(1, 12 * mm),
          p("项目定位", "h2"),
          p("学生上传简历与项目材料后，系统先定位可核验的原文件证据（文件、行号、版本、内容哈希），再由 DeepSeek 在证据上限内逐项解释岗位要求的支持程度、比较职业方向、生成可执行的补证任务。企业从岗位原文生成待确认要求，学生明确授权后企业才能查看对应的固定报告并进行人工核验回复。"),
          p("本系统评价的是材料对岗位要求的支持程度，不认证个人能力、本人贡献、代码运行结果或录用概率。", "disclaimer"),
          PageBreak()]

# ---------------- 1 项目概述与需求分析 ----------------
story += title("1 项目概述与需求分析")
story += [p("1.1 问题背景", "h2"),
          p("校招与实习筛选中，简历自述无法核验与企业关键词误判同时存在：“熟悉 PostgreSQL”可能来自一个依赖声明、一段抄来的代码或一次真实的线上运维；关键词匹配把三者打同一个分。学生不知道差距具体缺哪份材料，企业不敢相信筛选结果，双方都缺少一个指向原始证据的共同事实层。"),
          p("1.2 目标用户与核心需求", "h2"),
          table([
              ["用户", "需求", "CareerProof 的回应"],
              ["学生", "知道哪些声明有证据、缺什么、补什么最可能提升", "证据报告＋缺口任务＋新版材料对比与补证建议"],
              ["企业", "可信地横向对照候选人与岗位要求，且不越权看私有材料", "学生授权后的固定报告对照矩阵＋核验问题＋人工回复"],
              ["双方", "沟通状态可跟踪，结论可回溯到原文", "双端通知中心＋报告引用直达原文件行号"],
          ], [20 * mm, 62 * mm, 83 * mm]),
          Spacer(1, 5 * mm),
          p("1.3 产品形态", "h2"),
          p("Web 应用为主要呈现形态（PC 与 390px 移动视口均验收）：学生端覆盖材料上传、任务进度、报告复核、职业规划与补证成长闭环；企业端覆盖岗位定义、授权投递对照、核验回复。后端仅作为账号、材料解析与 AI 能力的接入层。"),
          p("1.4 边界声明", "h2"),
          p("系统输出“材料支持程度”，不输出能力认证；4–5 级证据需要运行记录或独立验证，当前 AI 自动评级上限为 3 级；企业不能读取学生未授权的任何私有材料。", "small"),
          PageBreak()]

# ---------------- 2 系统架构设计 ----------------
story += title("2 系统架构设计")
story += [p("2.1 技术栈", "h2"),
          table([
              ["层", "技术", "说明"],
              ["前端", "Next.js 15 App Router、React 19、TypeScript（strict）、Tailwind CSS", "20/23 页面为 Server Component；交互岛客户端化；零第三方 UI 依赖"],
              ["前端交互", "SSE＋轮询降级、错误边界、路由骨架屏、图表按需动态加载", "任务进度实时可见；连接中断自动降级；渲染异常不白屏"],
              ["后端", "FastAPI、SQLAlchemy（async）、PostgreSQL＋pgvector、Alembic", "API→Services→Repositories 分层；迁移与结构检查纳入验收"],
              ["AI 接入", "DeepSeek 官方 API（deepseek-flash，文本与视觉共用 Key）", "Provider 抽象＋端点域名白名单；Key 仅存后端环境变量"],
              ["本地 AI", "RapidOCR（ONNX）与多语言 MiniLM 语义模型，模型权重按 SHA-256 固定校验", "OCR 与语义检索不依赖云端；模型缺失自动保留词法/规则链路"],
              ["工具协议", "MCP 官方 SDK（stdio 只读服务器）＋ OpenAI Function Calling", "内部补检索用 Function Calling；能力导出用 MCP"],
          ], [22 * mm, 70 * mm, 73 * mm]),
          Spacer(1, 5 * mm),
          p("2.2 端到端数据流", "h2"),
          table([
              ["阶段", "输入 → 输出", "关键约束"],
              ["材料解析", "ZIP/PDF/DOCX/图片 → 带版本与行号的文本块", "独立子进程解析（可 kill、有超时）；ZIP 静态扫描；上传代码从不执行"],
              ["候选检索", "岗位要求 → 证据片段候选", "固定检测器＋BM25 风格词法＋本地 ONNX 语义三层；候选不直接改变规则分数"],
              ["受控规划", "证据上下文 → 补检索决策或停止", "最多两轮；白名单工具；为最终报告预留输入预算"],
              ["模型分析", "必要要求与片段 → 结构化 JSON", "外发同意＋脱敏＋单报告/日级/并发三层预算＋180 秒超时"],
              ["校验落库", "JSON → 持久化报告", "引用白名单、评级上限、约 20 类接地规则；失败一次定向修正重试"],
              ["展示与闭环", "报告 → 对照/规划/成长/通知", "SSE 进度；异常被动降级为规则报告并标明原因；人工复核可纠错"],
          ], [24 * mm, 62 * mm, 79 * mm]),
          Spacer(1, 5 * mm),
          p("2.3 架构原则", "h2"),
          p("① 规则定界、AI 解释、人工纠错：检索层决定候选与评级上限，模型只在边界内解释与初评，用户可采纳、驳回或备注；② Agent 不直接接触数据库，只能调用白名单只读工具；③ 所有关键判断留痕：提示词版本、工具调用事件、用量与降级原因写入报告元数据，可回放审计。", "body"),
          PageBreak()]

# ---------------- 3 AI 技术方案 ----------------
story += title("3 AI 技术方案")
story += [p("3.1 模型选型与集成方式", "h2"),
          p("选型理由：统一使用 DeepSeek 官方 API（deepseek-flash），因为：① Function Calling 与结构化输出稳定，适合受控工作流；② 同一 Key 覆盖文本与视觉两类能力，密钥治理简单；③ 成本可控，配合三层预算可精确限量；④ 官方端点合规清晰。历史上千问、智谱、百炼适配器仅作离线回归用途，产品路由已禁用。"),
          p("集成方式：Provider 抽象基类统一重试（仅 429/5xx/超时，指数退避并尊重 Retry-After）、端点域名白名单校验防止端点被改，以及 thinking:disabled 成本控制；提示词三处独立版本化——证据分析 evidence-trust-v29、视觉 visual-claim-v2、职业规划 career-plan-v11，版本号写入报告元数据；核心证据约束策略外置于 evidence_policy.md，与代码同仓库评审。"),
          p("输出治理：严格 Pydantic 契约（extra=forbid）＋单括号 JSON 修复计数＋校验失败后带 validationFeedback 的一次定向修正重试，仍失败则放弃该输出，不降标准放行。"),
          p("3.2 受控 Agent 工作流", "h2"),
          p("run_evidence_workflow 实现规划—工具—反思循环：模型经 Function Calling 自主决定调用 retrieve_more_evidence 在冻结材料上执行本地定向检索，每轮最多一次；或调用 get_previous_report_context 读取本人上一份同岗位报告；或直接停止。最多两轮，每轮重估剩余预算并为最终报告预留输入额度。所有工具调用以结构化事件（工具名、轮次、查询、作用域、状态）写入报告元数据，页面对用户可见。已用真实模型验证：模型能自主补取缺失证据（如 45 行长函数尾部）并停止于无增益轮次；一次真实报告消耗 7,667 输入/488 输出 Tokens，两条引用与 ZIP 原文哈希一致。"),
          p("该工作流是“单工具族、受控范围”的设计选择：可审计、可回放，优先于不可控的通用自主 Agent。", "small"),
          p("3.3 检索增强（RAG）", "h2"),
          table([
              ["层", "实现", "边界"],
              ["固定检测器", "依赖声明、空实现、函数覆盖等代码结构检测", "定义评级天花板，模型不可突破"],
              ["词法层", "自实现 BM25：camelCase 拆分、中文 bigram、IDF＋技能精确命中＋代码信号加成、每文件多样性限制", "覆盖代码与文本，不依赖外部服务"],
              ["语义层", "本地 ONNX MiniLM 多语言模型（提交与权重 SHA-256 固定，禁止运行时下载），阈值 0.33，每要求最多 2 命中", "仅作用于文档类文件，候选强度标 low，只支撑相关性判断，不能提高操作/任务等级"],
              ["向量层", "pgvector 存储 local-hash-v1 哈希特征（1024 维，属主隔离检索）", "明示为词袋投影而非语义 embedding，作为零依赖兜底"],
          ], [22 * mm, 84 * mm, 59 * mm]),
          Spacer(1, 4 * mm),
          p("评测：64 例冻结合成对照集（含跨文件缺失与近义干扰）——语义层把跨文件缺失场景召回从 0.5 提升到 0.8；近义干扰候选 100% 送达判定层但按设计不提升评级；剩余 4/10 跨文件 top-2 缺一为已归因的已知边界（词典两词阈值），不作展示层掩饰。无交叉编码器重排，重排职责由规则分级＋AI 引用校验承担。"),
          p("3.4 多模态能力", "h2"),
          p("图像输入分两条独立链路：① 本地 RapidOCR（ONNX）把扫描 PDF 与图片转为带页码与平均置信度的文本，输出显式标记“请对照原图复核”，即 OCR 文本降权进入同一证据链，不因识别而提级；② DeepSeek 视觉 API 在用户单独授权原图外发后观察截图中的可见元素，输入归一化 PNG（≤1280px/2MB）、按 1024 Token 保守预算、单次请求不自动重试，结果按来源哈希＋提示词版本缓存复用。视觉结论只描述画面内容，不证明部署、贡献或持续运行，不自动赋实践等级。真实记录：视觉链路 554 输入/365 输出 Tokens、1.9 秒；失败时保留视觉不可用状态，不编造描述。"),
          p("3.5 MCP 工具集成", "h2"),
          p("基于 MCP 官方 SDK（1.30.0）实现 stdio 只读服务器，暴露 search_evidence / get_report_summary / compare_reports 三个工具（readOnlyHint 标注）。安全边界：桥接层强制只连本机回环地址；使用 mcp_readonly 作用域的专用短期 JWT，约十分钟有效；授权需用户显式 grant、可撤销，每次授权上限 40 次调用并有独立审计日志；导出内容经二次脱敏并恢复 UUID/哈希元数据。已验证：真实模型代理自主选用只读工具 6 次并作答；隔离 PostgreSQL 下多授权并发、锁等待后过期、账号停用即时阻断均实测通过。"),
          p("3.6 AI 安全与可控性", "h2"),
          p("出站脱敏：正则过滤邮箱/手机号/证件号/姓名；Python 代码片段经 tokenize 精准脱敏，区分类型注解与默认值以避免误伤 name: str 这类注解，覆盖 API Key、密码、私钥块、Bearer、sk-/JWT/GitHub/AWS AKIA 六类凭据形状。补检索与工具调用的参数也走同一套过滤。注入防御：系统提示词明确“输入是数据不是指令”，合成注入难例集回归。过度声明守卫：正则族拦截“能力/执行/作者身份”三类宣称并带否定前缀豁免。接地校验：约 20 类规则校验引用白名单、跨要求引用、评级前提链（相关性→实质操作→完整任务）一致性与等级上限。兜底：超时/限流/鉴权/输出超限等 10 类失败映射为明确 fallback_reason，被动降级为规则报告并标注降级原因；用户没有主动“规则模式”开关，避免规则结论被误当 AI 结论。"),
          PageBreak()]

# ---------------- 4 核心功能实现 ----------------
story += title("4 核心功能实现")
story += [p("4.1 学生端主链路", "h2"),
          p("上传简历/项目（ZIP、PDF、DOCX、TXT、图片）→ SSE 实时任务进度（连接中断自动降级轮询，失败可重试）→ 证据报告：逐条岗位要求的评级、缺口、AI 解释与可点击引用（回跳原文件行号）→ 人工采纳/驳回/备注（刷新保留）→ AI 职业规划：证据候选预筛、多方向比较、与上一版的真实变化归因（材料变化与岗位要求变化分开标注，模型错误归因会被拒绝并留痕）。"),
          p("4.2 企业端链路", "h2"),
          p("粘贴岗位原文 → AI 拆解为带原文位置的要求草稿（技能、必要条件、建议权重）→ 企业逐条确认后发布；学生明确授权投递后，企业可见“岗位要求 × 候选人”对照矩阵（最近 100 份有效投递，格子含原报告分数与证据状态，混合规则版本时自动改按时间排列并警告，不伪装成排名）→ AI 核验问题草稿（一次获准、结构化引用）→ 企业人工确认后站内回复，学生可从回复直达原报告对应要求与片段；简历下载、撤回均有状态与通知，撤回即失去访问。"),
          p("4.3 补证成长闭环", "h2"),
          p("报告缺口 → 生成补证任务 → AI 产出结构化草稿（交付物、步骤、核验条件，明确未实现时要求先补具名实现而非只交运行日志）→ 人工编辑采纳 → 上传新版材料 → 新报告与固定基准逐项对比 → 变化进入职业规划。企业原投递快照不变，防止补证污染历史对照。"),
          p("4.4 双端通知中心", "h2"),
          p("投递、查看、下载、回复、撤回等事件事务性写入，收件人隔离、未读计数、授权跳转（跳转前复核授权，失效即拦）。首期为站内通知，不做站外邮件发送。"),
          p("4.5 前端工程质量", "h2"),
          table([
              ["项", "现状（2026-10-02 实测）"],
              ["类型安全", "TypeScript strict 全量开启；src 内 0 处 any / as any / ts-ignore"],
              ["实时体验", "SSE 三事件（progress/completed/failed）＋1.8 秒轮询降级＋四态连接状态展示"],
              ["健壮性", "根/全局错误边界（error.tsx、global-error.tsx）、统一 ErrorNotice 重试、任务级重试复用材料版本"],
              ["性能", "Server Component 为主；8 个路由骨架屏；SkillRadar 按需动态加载；共享 JS 102KB"],
              ["可访问性", "跳转主内容链接、focus-visible 全局描边、role=status/alert、aria 标注；390px 无横向溢出"],
              ["会话恢复", "未完成上传/核验按用户隔离暂存 sessionStorage（仅请求编号，不存敏感数据），刷新可续"],
          ], [28 * mm, 137 * mm]),
          PageBreak()]

# ---------------- 5 测试与部署 ----------------
story += title("5 测试、评测与部署")
story += [p("5.1 自动化回归（2026-10-02 本机全量实测）", "h2"),
          table([
              ["范围", "结果"],
              ["后端 pytest", "770 通过 / 20 跳过（SQLite 全量＋真实 PostgreSQL 并发/隔离专项）；Ruff 通过"],
              ["前端", "102 项 Node 测试通过；TypeScript 类型检查通过；Next.js 生产构建通过"],
              ["数据库", "Alembic upgrade head 与 alembic check 通过（11 个迁移）"],
              ["测试隔离", "全局关闭外部 AI；真实模型调用均为显式合成数据运行并留档"],
          ], [34 * mm, 131 * mm]),
          Spacer(1, 4 * mm),
          p("5.2 AI 评测与工程证据", "h2"),
          p("11 例固定难例（空实现、仅依赖、矛盾材料、伪造声明、提示注入）：8 例有证据获得模型正文，3 例无证据按生产策略跳过；64 例检索冻结合成对照（含跨文件与近义干扰归因）；v6→v22 提示词跨版本输出漂移检测脚本与基线 JSON 留档；每次真实调用的输入/输出 Token、耗时与模型名写入 AiUsageLog 并在页面展示。失败记录（如 run1 设计缺陷、预算不足降级）全部保留不覆盖，验收文档区分“通过”与“待验证”。"),
          p("5.3 部署与运行", "h2"),
          p("Docker Compose 提供 PostgreSQL＋pgvector；Start-Local.ps1 一键启动并做环境预检，Start-Demo.cmd 供课堂/评审演示，账号凭据存本机未入库文件。评审访问私有仓库按赛事规则授权。在线公网部署为可选项，当前未部署；如部署将启用 HTTPS、强密钥与既有日限额。"),
          p("5.4 已知边界与待验证（诚实清单）", "h2"),
          p("独立人工语义复核（项目外评审者签署）未完成；全鼠标上传链路验收未完成（当前为键盘流程）；语义检索缺更大规模项目外独立标注；4–5 级证据不自动授予；供应商账单未逐笔核对；语音模态未实现。以上不写作已完成。", "small"),
          PageBreak()]

# ---------------- 6 创新点 ----------------
story += title("6 创新点说明")
story += [p("6.1 技术创新", "h2"),
          table([
              ["创新点", "与常规做法的差异"],
              ["证据等级三判据链", "把“有关键词”拆为相关性→实质操作→完整任务，顺序成立才可评级；依赖声明、空实现、局部实现被结构性区分，模型自报等级与判据不符即拒绝"],
              ["引用可回溯到字节", "每条引用绑定项目版本、文件、行号与内容哈希，用户点击回跳原文高亮；模型不能改写这些锚点"],
              ["受控评级而非自由生成", "规则先定每条证据的评级上限，模型在上限内解释与初评，配合约 20 类接地校验与过度声明正则守卫，输出稳定可控"],
              ["双协议工具集成且全程审计", "内部补检索用 Function Calling（两轮受控规划），能力导出用 MCP 官方 SDK 只读服务器（短期 JWT、40 次上限、可撤销、独立审计），两种协议均真实模型验证"],
              ["多模态降权入链", "OCR 与视觉观察进入同一证据链但显式降权（置信度标记、“视觉不可用”不编造），不因多模态输入自动提级"],
          ], [34 * mm, 131 * mm]),
          Spacer(1, 4 * mm),
          p("6.2 应用创新", "h2"),
          p("① 把“补什么”变成可执行闭环：缺口任务→AI 结构化草稿（含核验条件）→新版材料→固定基准对比→规划归因，学生第一次能看到“补哪份材料最可能提升哪条要求”；② 三方信任链：企业核验问题→人工确认回复→学生直达原报告锚点，沟通围绕证据而非印象；③ 诚实对照视图：规则版本不一致时拒绝按分数排名并明示，防止跨报告误比。"),
          PageBreak()]

# ---------------- 7 总结与展望 ----------------
story += title("7 总结与展望")
story += [p("本项目以“证据链”为核心构建了学生成长与企业筛选的双端闭环：规则检索定界、DeepSeek 受控解释、人工复核纠错、全链路审计。工程上以 770＋102 项自动化测试、真实模型留痕与失败记录保留为质量底座；AI 深度体现在受控 Agent 工作流、三层 RAG、OCR/视觉双模态、MCP 只读导出与多层安全治理，而非单一对话功能。"),
          p("展望（按优先级）：① 完成项目外独立语义复核与更大检索标注集，把“引用合法”推进到“结论被证据支持”的外部证据；② 赛后开源：按 docs/发布许可决策.md 在 AGPL-3.0（保留 PyMuPDF）与替换为 pypdfium2 后采用宽松许可之间二选一；③ 可选公网演示部署；④ 语音模态（Web Speech API）与检索重排的进一步评测。"),
          p("8 提交材料状态", "h2"),
          table([
              ["材料", "状态（2026-10-02）"],
              ["代码仓库", "私有仓库已推送 104 个提交（2026-09-17 真实基线起）；评审访问按赛事规则授权"],
              ["技术文档", "本文件（候选稿 v2），≤30 页要求内"],
              ["演示视频", "脚本骨架已有；等待赛事具体通知后录制（5–8 分钟、1080p）"],
              ["团队信息", "广州软件学院 / B组 / jz（38419）/ 江博、郑振南 / 指导教师 杨斌（联系方式以报名系统为准）"],
              ["许可", "比赛期间私有；赛后开源前完成许可证决策（见 docs/发布许可决策.md）"],
              ["在线演示", "可选项，未部署"],
          ], [32 * mm, 133 * mm]),
          Spacer(1, 5 * mm),
          p("追溯材料：docs/DeepSeek统一路线与能力验收.md（能力矩阵与全部验收记录入口）；docs/赛前验收清单.md；docs/发布许可决策.md；backend/evals/（评测脚本与基线 JSON）；THIRD_PARTY_NOTICES.md。", "small")]

def keep_headings_with_body(flow):
    """小节标题（h2）与其后首个正文段落绑定同页，避免标题孤悬页底。"""
    result = []
    index = 0
    while index < len(flow):
        item = flow[index]
        next_item = flow[index + 1] if index + 1 < len(flow) else None
        if (isinstance(item, Paragraph) and item.style.name == "h2"
                and isinstance(next_item, Paragraph)
                and next_item.style.name in ("body", "small")):
            result.append(KeepTogether([item, next_item]))
            index += 2
        else:
            result.append(item)
            index += 1
    return result


OUTPUT.parent.mkdir(parents=True, exist_ok=True)
document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=21 * mm,
                             leftMargin=21 * mm, topMargin=25 * mm,
                             bottomMargin=23 * mm, title="CareerProof 技术文档候选稿 v2",
                             author="CareerProof 项目组 jz（广州软件学院）")
document.build(keep_headings_with_body(story), onFirstPage=page, onLaterPages=page)
print(f"{OUTPUT} pages={document.page}")
