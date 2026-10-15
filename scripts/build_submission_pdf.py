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
    add(f"文稿日期：{as_of}　产品功能基线：{revision}", "small")
    add("此基线是生成时的仓库HEAD，不是最终提交哈希。本文已更新当前功能说明，但不是候选版本全量验收或赛事提交证明。页数、视频规格和访问方式仍以最终赛事要求为准。", "small")
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
    add("当前证据：前端277项回归、类型检查与生产构建通过。正常站真实320px报告可直接查看两项部分支持的缺口，键盘切换和收起通过，5组来源默认关闭。首次独立用户与实际200%缩放仍待验证。", "small")

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

    heading(7, "当前验收与提交前缺口")
    grid([
        ["层次", "截至文稿日期的证据与限制"],
        ["真实页面", "合成双端撤回重投、通知定位与补证新版已实测；正常站320px报告及键盘切换通过。首次独立用户暂无法安排，实际200%缩放未验。"],
        ["当前源码检查", "全新安装的Python环境对当前后端：SQLite1318通过、56跳过；专属PG107通过，另8个真实硬停窗口通过，均零跳过。前端277、类型和生产构建通过。"],
        ["源码包 / CI", "预审包r4仍对应9a710d5，非当前最终候选。其独立解包、前端全新安装与后端后续全新安装分别留证。CI本地门禁通过，远端Actions未执行。"],
        ["AI与会话", "规则、Mock与真实AI语义分开，独立语义复核待完成。刷新原子轮换与跨标签模拟通过；真实同时过期、完整重放链和持久登录限流仍待完善。"],
    ])
    add("提交前必须补齐", "sub")
    add("冻结候选的复现与最终回归；首次独立用户反馈与真实AI语义复核；视频录制及完整回放；最终源码包的凭据与真实数据排除；第三方许可处置；评审访问和赛事格式确认；成员核对、签署与最终提交。10月22日停止新增功能、24日冻结候选、25日交付核对是项目目标，不替代官方截止。")
    add("原创、许可与边界", "sub")
    add("Codex、ZCode、DeepSeek Harness参与开发协作；参赛成员仍需理解代码并对最终核验负责。演示经历与指标是合成数据。第三方直接依赖见THIRD_PARTY_NOTICES.md，最终许可证与PyMuPDF发布方案尚待所有者确认，不把私有仓库或一份清单当作许可核验完成。")
    add("核对入口：docs/任务清单.md；逐项原始证据见20261015-refresh-atomicity、20261015-report-initial-group、20261014-browser-reconsent与20261015-source-regression。本稿未完成赛事格式确认、成员签署或最终上传。", "small")

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
