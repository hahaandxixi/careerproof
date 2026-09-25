"""Build the competition technical-document candidate from verified project facts."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
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
                            textColor=INK, alignment=TA_LEFT, spaceAfter=18),
    "subtitle": ParagraphStyle("subtitle", fontName="SimHei", fontSize=14, leading=23,
                               textColor=BLUE, spaceAfter=18),
    "h1": ParagraphStyle("h1", fontName="SimHei", fontSize=17, leading=27,
                         textColor=INK, spaceBefore=10, spaceAfter=12),
    "h2": ParagraphStyle("h2", fontName="SimHei", fontSize=11.5, leading=19,
                         textColor=BLUE, spaceBefore=11, spaceAfter=6),
    "body": ParagraphStyle("body", fontName="SimHei", fontSize=9.2, leading=16,
                           textColor=INK, spaceAfter=7),
    "small": ParagraphStyle("small", fontName="SimHei", fontSize=8, leading=13,
                            textColor=GRAY, spaceAfter=5),
    "cell": ParagraphStyle("cell", fontName="SimHei", fontSize=8.3, leading=14,
                           textColor=INK),
    "cover": ParagraphStyle("cover", fontName="SimHei", fontSize=10, leading=18,
                            textColor=GRAY, spaceAfter=7),
}


def p(text, style="body"):
    return Paragraph(text, styles[style])


def title(text):
    return [p(text, "h1"), HRFlowable(width="100%", thickness=1, color=BLUE), Spacer(1, 10)]


def table(rows, widths):
    data = [[p(str(value), "cell") for value in row] for row in rows]
    result = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SOFT),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CEDAE6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return result


def page(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#D8E3ED"))
    canvas.line(21 * mm, height - 18 * mm, width - 21 * mm, height - 18 * mm)
    canvas.setFont("SimHei", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(21 * mm, 15 * mm, "CareerProof · 技术文档提交候选稿 · 2026-09-25")
    canvas.drawRightString(width - 21 * mm, 15 * mm, str(doc.page))
    canvas.restoreState()


story = []
story += [Spacer(1, 32 * mm), p("职证 CareerProof", "title"),
          p("证据驱动的 AI 职业规划与岗位要求拆解", "subtitle"),
          HRFlowable(width="100%", thickness=2, color=BLUE), Spacer(1, 15 * mm),
          p("全国高校 AI Web 开发挑战赛 · 技术文档提交候选稿", "cover"),
          p("版本日期：2026 年 9 月 25 日", "cover"),
          p("学校、参赛组别、团队成员、指导教师和私有仓库访问方式：待参赛者填写。", "cover"),
          Spacer(1, 16 * mm),
          p("项目定位", "h2"),
          p("学生上传简历与项目材料后，系统先定位可核验的原文件证据，使用 DeepSeek 官方 API 对证据边界进行解释、给出职业方向比较和下一步补证任务。企业可以把自然语言岗位描述拆成带原文引用的要求草稿，并在人工确认后发布。"),
          p("本系统评价的是材料对岗位要求的支持程度，不认证候选人能力、本人贡献或录用概率。", "small"),
          PageBreak()]

story += title("1 真实问题与 Web 产品")
story += [p("传统关键词匹配会把依赖声明、简历自述、空函数和可运行实现混在一起。CareerProof 将结果拆成“已见事实、仍缺证据、下一份可提交材料”，让学生和教师能直接打开原文件核对。"),
          p("学生端链路", "h2"),
          p("上传简历与项目 ZIP/PDF/DOCX/图片 → 等待异步解析 → 查看材料预览 → 按岗位生成证据报告 → 点击引用核对原文件与行号 → 人工采纳、驳回或标记修正 → 生成跨职业规划并比较新版本变化。"),
          p("企业端链路", "h2"),
          p("企业粘贴岗位原文 → AI 提取技能、必要条件、建议权重与原文位置 → 企业逐条核对并确认 → 保存草稿或发布。生成 AI 草稿本身不会创建或公开岗位。"),
          p("主要界面", "h2"),
          table([
              ["界面", "核心可见能力"],
              ["材料中心", "上传、版本历史、解析预览、原文件与引用行定位"],
              ["岗位与任务", "自然语言岗位拆解、材料选择、外发授权、SSE 阶段状态"],
              ["报告与规划", "证据评级、来源片段、AI 与规则状态、补证建议、人工复核、跨版本变化"],
          ], [39 * mm, 126 * mm]),
          Spacer(1, 7 * mm),
          p("Web 应用是主要呈现形态；后端承担账号权限、材料解析、模型接入、引用校验与数据持久化。", "small"),
          PageBreak()]

story += title("2 技术架构与数据流")
story += [p("Next.js 15、React 19 与 TypeScript 组成前端；FastAPI、SQLAlchemy、PostgreSQL/pgvector 和本地文件存储组成后端。浏览器通过同源代理调用 API，认证 Cookie 保持 HttpOnly。"),
          table([
              ["阶段", "输入与输出", "关键约束"],
              ["材料解析", "简历、项目和扫描图片 → 带版本与行号的文本", "ZIP 静态扫描；不执行上传代码；OCR 置信度需人工核对"],
              ["候选检索", "岗位要求 → 证据片段", "固定检测器与有界词法候选；可选本地语义文档召回；候选不直接加分"],
              ["模型分析", "必要要求、缺口和片段 → JSON 解释", "外发同意、脱敏、预算、超时与并发限制"],
              ["工具与校验", "一次受控补检索 → 引用白名单校验", "只读当前上传索引；伪造引用、越权或非法等级拒绝"],
              ["结果展示", "持久化报告 → SSE/页面/历史", "异常被动降级；保留规则报告与人工复核"],
          ], [29 * mm, 63 * mm, 73 * mm]),
          Spacer(1, 6 * mm),
          p("检索边界", "h2"),
          p("pgvector 中的 local-hash-v1 不是语义 embedding。可选本地 ONNX 模型仅补充文档候选召回；目前缺少足够大的独立召回评测，不声称全职业语义 RAG 能力。"),
          p("Agent 边界", "h2"),
          p("模型最多调用一次 retrieve_more_evidence，只能读取当前材料索引中的有限片段。它体现了受控 Function Calling 与工具审计，不宣称通用自主 Agent 或 MCP 集成。"),
          PageBreak()]

story += title("3 AI 机制与可信度")
story += [p("AI 不只改写统计摘要。它在规则选出的材料片段内逐项解释岗位要求、指出信息不足、比较不同职业方向并提出可验收的补证任务；企业端还负责从岗位原文生成待确认要求。"),
          p("证据约束评级", "h2"),
          p("统一 1–5 级描述实践证据，但自动 AI 初评目前仅开放到 3 级。相关性、实质操作、完整任务三个判据须顺序成立，且引用必须属于当前要求的白名单。模型不能改变原文件、行号、内容哈希或人工复核结论。"),
          p("从引用到原文", "h2"),
          p("报告与职业规划保留项目版本、文件 ID、行号和可见片段。点击规划引用可打开对应项目文件并高亮引用行。原样重传材料只提示版本变化；只有可见引用片段改变才记为新增证据。"),
          p("多模态能力与边界", "h2"),
          p("本地 RapidOCR 把扫描 PDF 与图片转为带页码、置信度的文本，再进入同一证据校验链。OCR 能识字，但不证明视觉场景理解、作者身份或代码运行结果。"),
          p("安全与故障控制", "h2"),
          p("模型端点和型号固定；外发前按规则脱敏常见直接标识符。没有证据时跳过外部请求；模型限流、超时、结构不合格、非法引用或请求失败时被动保留规则结果，并标明降级原因。"),
          PageBreak()]

story += title("4 验收与结果边界")
story += [p("以下为本机仓库与浏览器的工程验收，不等于官方评分或跨人群招聘准确率。"),
          table([
              ["验证项", "已核验结果"],
              ["后端回归", "229 项通过；Ruff 检查通过"],
              ["前端回归", "18 项 Node 测试、TypeScript 类型检查、生产构建通过"],
              ["真实模型链路", "合成简历和项目可生成 DeepSeek 规划，比较软件、运营、数据方向并给出补证任务"],
              ["浏览器来源跳转", "规划引用打开 app/00_health.py，并高亮第 6–8 行；相同材料再次生成不误报新证据"],
              ["固定难例", "11 项合成案例：8 项有证据获得模型正文，3 项无证据按生产规则跳过；历史原始 JSON 格式缺陷已留档"],
              ["独立语义评测", "待项目成员以外的评审者签署；不能用引用 ID 合法率代替结论支持率"],
          ], [46 * mm, 119 * mm]),
          Spacer(1, 6 * mm),
          p("技术债与未覆盖项", "h2"),
          p("工作流只有一次受控补检索，没有多轮自主规划；语义文档检索缺大样本召回基准；多模态以 OCR 为主；MCP 未实现。4–5 级需要更强运行或独立验证证据，当前不自动授予。"),
          PageBreak()]

story += title("5 运行、隐私与提交状态")
story += [p("演示环境", "h2"),
          p("在 Windows + Docker Desktop 环境按 README 的干净环境复现流程安装依赖，并使用 Start-Demo.ps1 或 Start-Demo.cmd 启动。演示只使用 demo/ 合成数据；DeepSeek API Key 仅保存在本机未跟踪的环境文件。"),
          p("隐私原则", "h2"),
          p("学生报告默认只对本人开放，企业不能自动读取；模型调用前展示外发范围并要求主动同意。原图本地 OCR，外部模型只接收有界要求和必要片段。正式演示不得展示真实简历、环境变量或凭据。"),
          p("提交状态与待填信息", "h2"),
          table([
              ["项目", "截至本稿状态"],
              ["源代码", "GitHub 私有仓库 hahaandxixi/careerproof 已推送；按赛事要求提供评审访问"],
              ["PDF", "本文件为技术候选稿，页数需保持不超过 30；团队、组别、学校和官方模板待确认"],
              ["演示视频", "分镜脚本已有；5–8 分钟、1080p 正式成片尚待录制"],
              ["许可", "暂不公开源码；公开前需根据 PyMuPDF 的双许可约束选择发布许可"],
              ["在线演示", "本机一键启动已具备；公网部署属于可选项"],
          ], [38 * mm, 127 * mm]),
          Spacer(1, 5 * mm),
          p("追溯材料：README.md；docs/AI职业规划与岗位拆解-20260925.md；docs/DeepSeek可信度验收-20260918.md；docs/受控补检索FunctionCalling.md；docs/OCR多模态能力说明.md；docs/赛前验收清单.md。", "small")]

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=21 * mm,
                             leftMargin=21 * mm, topMargin=25 * mm,
                             bottomMargin=23 * mm, title="CareerProof 技术文档提交候选稿",
                             author="CareerProof 项目组")
document.build(story, onFirstPage=page, onLaterPages=page)
print(OUTPUT)
