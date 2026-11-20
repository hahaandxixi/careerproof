"""Build the review candidate, separating implemented behavior from release gates.

Uses reportlab and an installed Chinese TrueType font. No network, credentials,
models, services or database access. Run from any directory with --as-of YYYY-MM-DD.
"""
from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/pdf/CareerProof-技术文档-提交候选稿.pdf"
INDIGO = colors.HexColor("#4F46E5")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#526176")
PALE = colors.HexColor("#EEF2FF")
BORDER = colors.HexColor("#DCE3F1")
WIDTH = A4[0] - 44 * mm
FONT = "CareerProofChinese"
PAGE_COUNT = 23


class Architecture(Flowable):
    """A native vector diagram; this is architecture, not runtime evidence."""
    def __init__(self):
        super().__init__()
        self.width, self.height = WIDTH, 225

    def draw(self):
        c = self.canv
        def box(x, y, w, h, lines, accent=False):
            c.setFillColor(PALE if accent else colors.white)
            c.setStrokeColor(INDIGO if accent else BORDER)
            c.roundRect(x, y, w, h, 7, fill=1, stroke=1)
            c.setFillColor(INK)
            c.setFont(FONT, 10)
            for i, text in enumerate(lines):
                c.drawCentredString(x + w / 2, y + h / 2 + (len(lines)-1)*7 - i*14 - 3, text)
        def arrow(x, top, bottom):
            c.setStrokeColor(INDIGO)
            c.line(x, top, x, bottom)
            c.line(x, bottom, x-3, bottom+5)
            c.line(x, bottom, x+3, bottom+5)
        box(0, 178, WIDTH, 37, ["学生 / 企业浏览器", "Next.js · TypeScript · 原版靛蓝界面"], True)
        arrow(WIDTH/2, 178, 156)
        box(0, 108, WIDTH, 48, ["FastAPI 应用与异步任务", "角色与同意检查 / 冻结输入 / 引用校验 / 预算闸门"], True)
        w = (WIDTH-20)/3
        for i, lines in enumerate([
            ["PostgreSQL + pgvector", "报告 / 投递 / 事件 / 账目"],
            ["本地版本材料", "解析 / OCR / 静态检索"],
            ["DeepSeek 官方 API", "经单独同意的必要上下文"],
        ]):
            x = i*(w+10)
            arrow(x+w/2, 108, 83)
            box(x, 30, w, 53, lines)
        c.setFillColor(MUTED)
        c.setFont(FONT, 8)
        c.drawString(0, 8, "架构示意：不执行上传代码；外部模型不可绕过应用权限直接读取数据库。")


def build(output: Path, as_of: str, font_path: Path) -> None:
    datetime.strptime(as_of, "%Y-%m-%d")
    if not font_path.is_file():
        raise FileNotFoundError("Provide --font with an installed Chinese TrueType font")
    pdfmetrics.registerFont(TTFont(FONT, str(font_path)))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT, italic=FONT, boldItalic=FONT)
    styles = {
        "cover": ParagraphStyle("cover", fontName=FONT, fontSize=30, leading=42, textColor=INK, spaceAfter=16),
        "title": ParagraphStyle("title", fontName=FONT, fontSize=21, leading=29, textColor=INK, spaceAfter=15),
        "sub": ParagraphStyle("sub", fontName=FONT, fontSize=12, leading=20, textColor=INDIGO, spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle("body", fontName=FONT, fontSize=10, leading=17, textColor=INK, spaceAfter=9, wordWrap="CJK"),
        "small": ParagraphStyle("small", fontName=FONT, fontSize=8.3, leading=13, textColor=MUTED, spaceAfter=7, wordWrap="CJK"),
        "cell": ParagraphStyle("cell", fontName=FONT, fontSize=9, leading=15, textColor=INK, wordWrap="CJK"),
    }
    revision = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT).decode().strip()
    story = []
    def p(text, style="body"):
        return Paragraph(escape(text), styles[style])
    def add(text, style="body"):
        story.append(p(text, style))
    def heading(number, name):
        if story:
            story.append(PageBreak())
        add(f"{number:02d}  {name}", "title")
        story.extend([HRFlowable(width="100%", thickness=1, color=BORDER), Spacer(1, 12)])
    def grid(rows, widths=None):
        data = [[p(str(value), "cell") for value in row] for row in rows]
        table = Table(data, colWidths=widths or [WIDTH*.25, WIDTH*.75], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), PALE),
            ("GRID", (0,0), (-1,-1), .4, BORDER),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 9),
            ("RIGHTPADDING", (0,0), (-1,-1), 9),
            ("TOPPADDING", (0,0), (-1,-1), 9),
            ("BOTTOMPADDING", (0,0), (-1,-1), 9),
        ]))
        story.extend([table, Spacer(1, 10)])

    story.extend([Spacer(1, 34*mm), p("职证 CareerProof", "cover")])
    add("把岗位缺口，变成可完成的下一步。", "title")
    story.extend([HRFlowable(width="100%", thickness=3, color=INDIGO), Spacer(1, 12*mm)])
    add("比赛技术说明 · 评审预备稿", "sub")
    add("学生整理本人材料，查看带来源的岗位报告；企业核对明确授权的固定报告并具名沟通。")
    add("补证产生新版，旧投递保持原样。")
    add("学校：广州软件学院　参赛组别：B组")
    add("成员：江博、郑振南　指导教师：杨斌")
    add(f"文稿日期：{as_of}　产品功能基线：{revision}　文稿页数：{PAGE_COUNT}", "small")
    add("此基线是出稿时的实际仓库HEAD，不是最终提交哈希。本文已更新当前功能说明，但不是候选版本全量验收或赛事提交证明。页数与基线同时写入正文和页脚；视频规格和访问方式仍以最终赛事要求为准。", "small")
    add("阅读顺序：用户与任务 → 架构 → AI与证据 → 授权快照 → 补证闭环 → 复现 → 验收与交付。", "small")

    heading(1, "先回答用户该做什么")
    add("面向拥有本人简历与项目材料、准备实习或校招的学生，以及确认岗位要求并核对授权报告的企业人员。首个完整场景聚焦软件开发岗位，不承诺所有职业的自动评价质量。")
    grid([
        ["角色", "最短业务路线"],
        ["学生", "选择岗位与材料 → 生成并核对报告 → 明确授权投递。需要完善材料时，从一条缺口进入补证。"],
        ["企业", "确认并发布岗位要求 → 阅读本岗位已授权报告 → 对具体要求和证据发送站内问题。"],
    ])
    add("报告页的阅读顺序", "sub")
    add("先看已保存状态的一句话概括，再展开一组要求，最后按需打开原文。四组为有证据支持、部分支持、待补材料、未覆盖或需复核。优先展开有内容的待补材料；没有时依次展示部分支持、未覆盖或需复核、有证据支持，用户仍可切换和收起。计数和完整列表来自全部要求，不由最多3条建议决定。")
    add("已有建议按要求附加，保留本地规则提示、AI证据建议或人工复核后的真实来源。同一句缺口与建议只显示一次；没有建议的项不会为了填满界面而生成建议。")
    add("本人核对可选，投递独立完成", "sub")
    add("本人核对是可选意见记录，来源证据默认收起。学生仍在报告页明确阅读分享范围、同意后投递；本次重排没有增加强制补证步骤。报告定位保持岗位材料对照，尚未改成职业推荐页。")
    add("当前证据：接受页面提交 b91c255 的前端目标测试 16 passed；1280/390、键盘、加载/失败恢复和真实 200% 缩放已有本稿第 14 节记录。旧 277 项回归、旧 21 项和 CDP pageScale 结论已作废，不再混用。", "small")

    heading(2, "架构与可追溯数据")
    story.append(Architecture())
    add("版本材料与报告分离", "sub")
    add("原始简历、项目材料与解析结果按版本保存。报告绑定生成时选择的岗位与材料范围，引用保存可用的文件、行号或页码等定位信息与内容哈希。上传新版不改写旧报告，也不自动向企业分享。")
    grid([
        ["层次", "职责与边界"],
        ["前端", "Next.js / TypeScript；学生账户收纳个人材料、投递和通知，企业按所属岗位查看授权对照。候选独立构建使用Next.js 15.5.27。"],
        ["后端", "FastAPI / Python 3.12 / SQLAlchemy；处理权限、材料解析、异步任务、报告、站内事件和用量记录。"],
        ["向量与文件", "PostgreSQL + pgvector，当前知识向量384维；本地材料存储保留版本与哈希。"],
    ])
    add("模型不可用时，本地确定性哈希投影与规则结果仍需明确标注；有语义模型的索引与哈希索引不能混作同一检索尺度。上传的源代码只作静态分析，不执行。", "small")
    add("正常库已启用0019数据完整性迁移。先用一致性备份完成独立恢复与升级演练，再核对正常库升级前后全表摘要；除迁移版本外数据一致。测试库与正常库隔离，不为通过检查清理用户历史。", "small")

    heading(3, "AI解释受证据与预算约束")
    add("先限定证据，再解释与初评", "sub")
    add("规则检索先限定候选原文和评级上限。外部模型在必要上下文内解释证据、初评与规划补证，输出经过引用白名单、来源对应和表达校验；非法引用、失败或限额不能伪装成可靠结论。")
    grid([
        ["环节", "已实现的约束"],
        ["受控规划", "最多两轮工具规划，针对本次冻结材料补取证据，或读取本人同岗位历史解释。历史解释不替代当前原文。"],
        ["输出校验", "校验要求身份、引用和判据，允许有界定向修正。模型解释与规则结果分别保存，不把合法引用当作语义正确的充分条件。"],
        ["发送边界", "文字外发需配置可用、用户同意、角色与材料检查及预算准入。未同意仍可保留规则报告。必要上下文脱敏不等于全面隐私保证。"],
        ["用量事实", "核验与主匹配记录物理请求、可信收据、幂等账目及在途预留；没有可信收据保留unknown，不把失败或未知计为零。"],
    ])
    add("多模态与工具", "sub")
    add("本地OCR与单独授权的外部图片观察分开记录。截图只支持可见内容描述，不证明运行成功、本人贡献或部署。可选MCP只读导出另受短期授权与撤销检查，不能借此读取未授权材料。")
    add("产品外部生成统一使用DeepSeek官方API。开发协作客户端的额度与产品模型预算分别管理；本文没有调用模型，也没有据历史余额推算当前费用。", "small")
    add("不勾选外部AI同意也可先生成本地规则报告；这不等于真实AI调用成功。Redis静态识别已支持类型参数的读写调用，新评级口径仅用于新报告，历史报告和原投递不回填。真实生成语义及贡献仍需独立核对。", "small")

    heading(4, "投递分享的是固定报告")
    grid([
        ["阶段", "可观察行为"],
        ["明确投递", "学生阅读并确认本次分享范围，授权岗位所属企业访问当次固定报告、引用与该次简历下载。发布岗位不会自动获得学生库访问权。"],
        ["企业沟通", "企业按要求联动证据，可填写站内回复。AI问题草稿需要企业核对后明确发送，不能自动代发。"],
        ["通知定位", "学生从账户菜单进入通知，核对授权后定位相应投递和原报告；站内事件不等于邮件送达。"],
        ["撤回", "企业沿旧授权访问报告、下载、回复及旧企业通知目标应被拒绝；学生仍可查看本人历史报告。已下载副本无法通过撤回追回。"],
        ["重新投递", "再次明确同意后产生新授权记录。旧记录与回复保留，新记录不继承旧回复；不会把旧链接重新变成有效授权。"],
    ])
    add("授权范围与固定快照", "sub")
    add("学生私人补证任务和新报告不自动替换企业已有快照。企业对照的颜色表示已保存材料支持状态，数值来自投递当时的报告，不重新评分，不把查看或下载解释为录用进展。")
    add("验证范围", "sub")
    add("沿同一合成运行已完成撤回旧授权 → 明确投递新版 → 企业SQL引用与回复 → 学生通知定位的真实页面链。独立HTTP核对旧详情、查看、下载、回复及两条旧企业通知均拒绝；原6份快照未变，新快照等于已保存新版报告。这证明指定合成场景，不替代首次用户或真实材料验收。")

    heading(5, "从一条缺口到新版报告")
    grid([
        ["动作", "结果与边界"],
        ["1 选缺口", "从报告对应要求开始，核对原文与缺口。已有任务时进入原任务，不要求重复创建。"],
        ["2 定交付物", "填写交付物、步骤和核验条件。合格AI草稿可补入空白项，保存前仍可本人修改。"],
        ["3 保存新版", "上传新版简历或项目并保存本次材料选择。临时改选和上传本身不改变已保存分析范围。"],
        ["4 生成与对照", "主动生成新报告，对照任务固定基准，分别核对材料变化、岗位要求、引用、状态和解释。没有升级也是有效结果。"],
        ["5 决定分享", "新报告仅本人可见；如需分享新版，按现有授权状态撤回旧投递并重新确认，企业旧快照不自动覆盖。"],
    ])
    add("逐项核对变化", "sub")
    add("任务里的固定基准与报告页的上一份同岗位报告可能不同。展示补证闭环时应说清比较对象，不能把换岗位、补材料或本人采纳直接解释为能力提升。")
    add("证据等级与图形", "sub")
    add("当前自动判定至实践证据3级；4、5级未开放授予。未找到材料不等于没有能力，仅自述或规则不支持不授予等级。不汇总能力总分，不以雷达面积或材料支持度推断录用概率。")
    add("正常站已实际完成从Redis缺口保存任务、上传具名v2、解析、选择并保存新版、未授权外发生成规则报告及逐项对照。旧8份投递快照哈希保持不变；新版材料与规则版本分别标记，规则修正不能冒充学生能力提升。", "small")

    heading(6, "本地复现与合成演示")
    add("先按仓库说明准备依赖与本机配置，再启动Docker Desktop并等待引擎就绪。正常站已完成按自有进程身份停止、构建与原库恢复；最终冻结候选仍需重新核对，不能仅凭入口脚本存在判定可复现。")
    grid([
        ["入口", "用途"],
        ["Start-Local.ps1", "普通本地服务，3000/8000，不初始化演示账号。先运行 -CheckOnly 核对已安装环境。"],
        ["Start-Demo.cmd", "复用普通服务，另准备合成账号、岗位和材料。已有演示不为恢复展示反复播种。"],
        ["scripts/Start-E2E.ps1", "专属运行ID、cp_e2e数据库、存储与构建，3001/8001；关闭外发、使用合成模型，与普通账号不互通。"],
        ["停止与恢复", "只操作已核对身份的自有进程，保留数据卷与失败记录。停止数据库前确认没有其他验收服务使用它。"],
    ])
    add("最短体验路线", "sub")
    add("从演示页下载或导入同编号材料，等解析完成 → 选择对应岗位与版本 → 不勾选外部AI同意，先生成规则报告 → 按需查看引用 → 阅读分享范围、勾选同意、确认投递。已导入的材料无需重复上传，本人核对备注可选。企业回复、通知与补证另沿现有演示说明继续。")
    add("预设热力图不需要登录，只演示交互，不创建投递或调用模型。读取已保存报告、合成实时生成、规则降级和真实模型调用必须分开讲解。不要拿3001账号登录3000。")
    add("账号只在本机凭据文件读取，源码包不附密码或API Key。运行细节见 docs/guides/使用与启动.md、docs/guides/功能演示.md；普通与隔离入口不得混用数据库和材料。", "small")

    heading(7, "当前验收、截止与交付边界")
    grid([
        ["项目", "本稿可写的当前事实"],
        ["页面结果", "学生报告页的固定材料版本、下一步、移动端步骤提示已进入接受提交 b91c255；1280/390、加载失败恢复和键盘路径有实际页面证据。"],
        ["200% 验收", "在 1280×900 GUI Chrome 前台窗口用系统 Ctrl+Shift+= 放大到 innerWidth=640、DPR=2；不是 CDP pageScale。"],
        ["构建", "接受文件集构建 exit 0，19 页面；BUILD_ID _MAQzEIqP5DEgV9hioxr_；3108 仍加载旧构建 WDMAX7DoSVpEqnsSppkxf。"],
        ["人工复核", "原始表 12 处待填；江博 v2 已填 M01、M02/M03 部分，仍有 8 处待填；不据此关闭 D。"],
    ])
    add("截止口径", "sub")
    add("校内截止：2026-11-15；省赛：2026-11-18；国赛：2026-12-27。截止日期不替代候选冻结、出包、人工复核和赛事格式确认；这些交付动作仍须按各自状态登记。")
    add("交付边界", "sub")
    add("本稿不把 staging 当候选包，不把旧视频初稿当成片规格，不把旧 8 页 PDF 当当前交付。最终包、最终视频、人工 3/3 与成员签署仍未完成。", "small")

    heading(8, "预算账本：42k / 49,499 / 60k 的算术")
    add("历史运行的规划与分析 wire 估算分别为 10,653 与 38,846 bytes，合计 49,499 bytes。42,000 bytes 的预算门槛小于实际合计，因此在 admission 阶段拒绝，未产生物理请求；60,000 bytes 覆盖本次无工具、无修复路径，余量 10,501 bytes，才允许两次物理请求。")
    grid([
        ["量", "数值", "意义"],
        ["规划 wire", "10,653", "历史请求的 UTF-8 wire 估算"],
        ["分析 wire", "38,846", "历史请求的 UTF-8 wire 估算"],
        ["合计", "49,499", "10,653 + 38,846；小于 60,000"],
        ["预算门槛", "42,000 / 60,000", "42k 拒绝；60k 准入；60k 非供应商 token 上限"],
        ["实际 usage", "11,137 / 1,679", "实际计费输入/输出 tokens，不等于 wire 字节"],
    ])
    add("42k/60k 是同一 wire 口径的准入值；不能把 bytes 与 tokens 混算，也不能把 60k 写成每次都会用满。本账本未调用模型，仅复核保存数据与估算函数。", "small")

    heading(9, "证据验证器：五项本地校验")
    add("本地 verifier 只读保存报告与固定 ZIP，不执行上传代码，不调用模型。五项核心检查如下：")
    grid([
        ["检查", "判定"],
        ["引用位置", "filePath 必须能解析到固定 ZIP；行号有效，行范围不超过源文件，片段非空。"],
        ["引用完整", "每项至少有一个 citation ID；AI citation IDs 必须是该要求证据引用的子集。"],
        ["等级上限", "gap/claimed_only/unsupported 不得带等级；普通项等级不得超过本地 supported criteria 数。"],
        ["业务锚点", "Python 项核对约定业务锚点；Redis 在固定材料中未实现时必须保持 gap/null。"],
        ["用量与费用", "attempts、可信 usage、报告 aiUsage 必须一致；费用按输入/输出单价计算且不得超过上限。"],
    ])
    add("工具调用另有边界：completed 的 retrieve_more_evidence 必须有有效引用；没有 completed 调用则明确列为 UNVERIFIED，不伪造成功。错行号、错文件、越级、完成态无引用和缺 usage 的夹具均必须失败。", "small")

    heading(10, "源码等价四哈希链")
    add("历史运行副本与提交源码不是字节级同一文件；以下四个哈希点把差异限定在一行诊断输出和后续预算修复内，不能据此声称当前源码等价。")
    grid([
        ["哈希点", "SHA256（前 12 位）", "结论"],
        ["运行副本", "a571a225af50", "包含唯一诊断 print 的运行副本"],
        ["去 print 归一化", "691dbf73a466", "等于 bcbe0e3 的历史源码，historicalBusinessEquivalent=true"],
        ["预算修复后", "e76c04dd327b", "旧 path-check 记录的当前 workflow；与运行副本不逐字节一致"],
        ["本轮当前源码", "fc4b3d44d48c", "加入证据缺口回查后的实际当前文件；需重新按当前 HEAD 核验"],
    ])
    add("因此，四哈希链证明的是“运行副本去掉一行诊断输出后可还原历史业务文件”和“后续预算/缺口修复确实改变文件”，不是旧报告与当前源码字节一致。", "small")

    heading(11, "staging r9：来源、清单与排除")
    grid([
        ["项目", "实际结果"],
        ["来源提交", "6f6a1b1de0cf8117ff5f096932a7945c2aada92d"],
        ["清单条目", "848"],
        ["逐文件核对", "0 mismatch / 0 missing"],
        ["解包专项", "23 passed；首轮 9 个 setup 错误是临时父目录不存在，不是包内容失败"],
        ["结论", "staging，不是候选包/冻结包"],
    ])
    add("staging 排除暂停的展示改动、未提交文档、PDF/视频最终稿、最终候选包和本地运行产物；即使包内专项通过，也不能代替页面、人工、真实 AI 语义或最终候选验收。")
    add("ZIP 的交付 SHA256 由命令按实际文件重算，长度必须为 64；README 已修正为 44c8e634269c635a6152795e05085e686ee8ae03a6aa4b9f4ddeef69c755e4d7。", "small")

    heading(12, "检索预过滤修复前后")
    add("pgvector 检索的过滤必须先于排序。修复前（fa8fbbd 之前）是先取近邻再在应用层过滤，HNSW 的 ef_search 预算可能把本人材料命中整批漏掉，尤其在 allowed ids 很多时。")
    add("修复后使用物化 CTE：先把允许的 source/chunk 物化为 owned_chunks，再在 CTE 列上计算 distance 并排序，最后取结果。代码层证据见 retrieval.py 的 MATERIALIZED 预过滤与注释；这不是本轮新改动。")
    add("未连 PostgreSQL、未执行 EXPLAIN，也未构造上千 allowed ids 的召回实验；运行时召回率仍标 UNVERIFIED，不能把代码层修复写成实测提升。", "small")

    heading(13, "证据被重复索要：修复与边界")
    add("固定 V2 的 pytest 要求实际只发送了 3 条证据；规则层 evidenceList 有 6 条，runtime/pytest-output.txt 等 3 条未发送。材料中 test_registration.py 有 10 个测试函数，实际只发送了第 1 个函数片段（29–39 行），其余 9 个没有进入模型上下文。")
    add("修复新增 evidence_scope.py，在保存 AI gap/suggestion 前回查该要求的规则层 evidenceList 全集：若存在未发送证据，则把“未展示/请补充”改为“本次片段未覆盖/材料中可能已包含”，并给出短名和行号；规则 narrative 的 explanation 也剥离内部 UUID。")
    add("边界仍然明确：只改措辞和回查，不改变检索、选证、评分或上下文上限；模型可见范围仍受 3 条证据和片段长度限制。当前源码 fc4b3d44d48c 尚未用新模型输出复验，不能声称模型现在能看见全部 10 个测试。", "small")

    heading(14, "页面验收：1280 / 390 / 200% / 键盘")
    grid([
        ["场景", "实际观察"],
        ["1280×900", "报告页显示固定材料版本与下一步；证据入口默认收起，展开后可见引用。"],
        ["390×844", "步骤条出现横向滑动提示；滚到末端可见第 4/5 步；关键按钮可操作。"],
        ["真实 200%", "GUI Chrome 前台 Ctrl+Shift+=；innerWidth=1280→640，DPR=2；文档 scrollWidth=clientWidth=632，无整页横向溢出。"],
        ["键盘", "Tab 覆盖跳过入口、导航、步骤 1/2/4/5、返回报告、处理记录；未发现焦点陷阱。"],
        ["状态", "加载显示确认登录；阻断 API 显示错误与重新加载；解除阻断后实际点击恢复。"],
    ])
    add("接受构建 BUILD_ID 为 _MAQzEIqP5DEgV9hioxr_，前端目标测试 16 passed；旧 21 项结论已作废。200% 下步骤条自身的横向滚动与整页溢出要分开记录，不能把 CDP pageScale 当作浏览器缩放。", "small")

    heading(15, "固定报告、授权与撤回")
    add("投递分享的是投递时的固定报告和本次授权片段，不是学生当前全部材料。学生必须明确同意；企业只能沿该岗位授权入口读取固定报告、引用和本次简历下载。")
    add("撤回后，企业沿旧授权访问报告、下载、旧回复和旧通知目标应被拒绝；学生仍可查看本人历史报告，但已下载副本不能追回。重新投递需要再次明确同意，旧回复不继承，也不能把旧链接恢复为有效授权。")
    add("这些是既有授权行为；本稿不重新跑企业业务、不操作正常库、不声称新增授权或候选冻结。", "small")

    heading(16, "从缺口到新版报告")
    add("补证任务先绑定一条岗位要求和固定基准，再上传具名新版材料；上传或临时改选本身不改变已保存分析范围。学生主动生成新报告后，对照材料、要求、引用、状态和解释；没有升级也是有效结果。")
    add("新报告只属于本人；如需企业查看新版，必须按现有授权状态撤回旧投递并重新确认。旧企业快照不自动覆盖，企业查看或下载不等于录用进展。", "small")

    heading(17, "人工复核：不适用选项与 8 处待填")
    add("人工复核表新增“不适用”：某检查项对当前材料不适用时，结论列填“不适用”并写理由。例如材料本身不是空实现，则“是否识别空实现”不适用。不得代填，也不得改已有判词。")
    grid([
        ["口径", "当前状态"],
        ["原始表", "12 处待填"],
        ["江博 v2", "填了 M01、M02/M03 部分"],
        ["仍待填", "8 处"],
        ["是否计入通过率", "否；不据此关闭 D，不代签"],
        ["当前结论", "人工 3/3 未完成；机器和另一模型不能冒充真实人员"],
    ])
    add("本稿没有填写任何人工判词，也没有把不适用选项当作完成证据。", "small")

    heading(18, "交付材料与视频状态")
    add("当前 output/video/ 没有选定成片；六份旧稿已归档到 output/video/archive/20261021-old-drafts/，ARCHIVE-MANIFEST.json 已核。旧稿的时长、分辨率和剪辑只能作为历史，不得当作最终成片规格。")
    add("本稿是 2026-10-22 重制的 23 页技术说明，不是最终候选包；旧 8 页 PDF 已归档为历史，不覆盖其原始用途。视频需按完整项目实际实现重新录制，另行安排。")
    add("源码包、最终视频、人工 3/3、成员签署和赛事格式确认仍未完成；不重新出包、不冻结、不推送。", "small")

    heading(19, "风险、未验证与数据边界")
    grid([
        ["风险", "当前边界"],
        ["模型可见范围", "修复只改措辞；上下文仍限 3 条证据，10 个测试函数中的 9 个未发送。"],
        ["规则投影", "path-check 曾在当前工作树因源码已演进出现 drift；历史 pass 只按其保存值引用，不冒充当前重跑。"],
        ["prefilter", "代码层 MATERIALIZED 修复存在；未连 PG/EXPLAIN，运行时召回率 UNVERIFIED。"],
        ["人工", "8 处待填；N/A 只表示不适用，不是通过。"],
        ["交付", "staging 不是候选包，3108 仍是旧构建，视频无成片。"],
    ])
    add("所有演示材料、指标和测试输入均为合成数据。未调用真实模型，未重算规则报告，未重新出包，未操作正常业务记录。", "small")

    heading(20, "协作披露、许可与原创边界")
    add("Codex、ZCode、DeepSeek Harness 参与开发协作；参赛成员仍需理解代码并对最终核验负责。演示经历与指标是合成数据，不把生成工具写成能力认证或人工评审替代。")
    add("第三方直接依赖见 THIRD_PARTY_NOTICES.md；许可证与 PyMuPDF 发布方案仍需所有者确认。文本描述、截图和合成材料不替代第三方许可核验、真实用户反馈或赛事格式确认。", "small")

    heading(21, "证据入口与复核命令")
    grid([
        ["主题", "入口"],
        ["页面与 200%", "docs/evidence/20261022-ui-accepted/README.md"],
        ["预算账本", "docs/evidence/20261021-input-budget-ledger/budget-reconciliation.json"],
        ["源码等价", "docs/evidence/20261021-source-equivalence/source-equivalence.json"],
        ["staging", "docs/evidence/20261021-source-staging/README.md"],
        ["证据回查", "docs/evidence/20261022-repeated-material-gap/README.md"],
        ["人工复核", "docs/guides/评测与人工复核.md"],
    ])
    add("复核时应先核对提交/构建/材料版本，再看结果；历史证据不自动改写为当前结果。PDF 的页数、基线、BUILD_ID 与 3108 旧构建均在本稿中明示。", "small")

    heading(22, "结论")
    add("本稿给出的可交付结论是：预算、证据校验、源码差异、staging、检索预过滤、页面和重复索证边界均有可追溯记录；人工、最终视频、候选包和冻结仍未完成。")
    add("交付继续以固定材料与固定报告为基础，不接受把未发送材料写成缺失、把历史 pass 写成当前通过、把旧节点写成新截止、或把 staging 写成候选包。")
    add("下一步：按 2026-11-15 校内截止倒排人工复核、PDF/视频/包和成员签署；任何真实模型请求须另行授权并记录模型、请求上限、费用上限和材料范围。", "small")

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.line(22*mm, A4[1]-15*mm, A4[0]-22*mm, A4[1]-15*mm)
        canvas.setFont(FONT, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(22*mm, 12*mm, f"CareerProof · 评审预备稿 · {as_of}")
        canvas.drawRightString(A4[0]-22*mm, 12*mm, str(doc.page))
        canvas.restoreState()
    output.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=22*mm,
        leftMargin=22*mm, topMargin=24*mm, bottomMargin=22*mm,
        title="CareerProof 技术文档 - 评审预备稿", author="CareerProof 项目组")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"Written: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--as-of", default=datetime.now(timezone(timedelta(hours=8))).date().isoformat())
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/simhei.ttf"))
    args = parser.parse_args()
    build(args.output, args.as_of, args.font)


if __name__ == "__main__":
    main()
