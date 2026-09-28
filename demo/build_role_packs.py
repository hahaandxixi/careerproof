"""Build nine named, paired synthetic upload packs and manual test scripts.

No credentials, network, models or execution of sample code. Assets are derived
from role-cases.json and owned sample sources; legacy download paths stay intact.
"""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

DEMO = Path(__file__).resolve().parent
ROOT = DEMO.parent


def load_cases():
    cases = json.loads((DEMO / "role-cases.json").read_text("utf-8"))
    jobs = json.loads((DEMO / "jobs.json").read_text("utf-8"))
    if len(cases) != 9 or len({c["caseId"] for c in cases}) != 9:
        raise ValueError("Exactly nine distinct named role cases are required")
    if {c["jobTitle"] for c in cases} != {j["title"] for j in jobs}:
        raise ValueError("Role cases must correspond to the published demo job catalog")
    return cases, {job["title"]: job for job in jobs}


def project_files(case):
    source = DEMO / (
        "evidence-api" if case["slug"] == "backend" else f"roles/{case['slug']}/project"
    )
    files = {}
    if source.exists():
        files = {
            p.relative_to(source).as_posix(): p.read_bytes()
            for p in sorted(source.rglob("*"))
            if p.is_file()
        }
    explanation = DEMO / f"roles/{case['slug']}/project.txt"
    if explanation.exists():
        files["作品说明.txt"] = explanation.read_bytes()
    if not files:
        raise ValueError("Missing role-specific project material")
    files["案例说明.txt"] = (
        f"测试案例：{case['caseId']} {case['title']}\n"
        f"作品：{case['projectTitle']}；材料版本：{case['version']}\n"
        f"配套简历：{case['resumeFilename']}\n配套岗位：{case['jobTitle']}\n"
        "合成静态练习，不对应真实个人或组织。脚本未执行，不证明本人贡献。\n"
        f"已知边界：{case['boundary']}\n"
    ).encode("utf-8")
    return files


def build(output=None):
    cases, jobs = load_cases()
    output = Path(output) if output else ROOT / "jianli/public/demo-assets/cases"
    output.mkdir(parents=True, exist_ok=True)
    for case in cases:
        skills = "、".join(
            r["skillName"] for r in jobs[case["jobTitle"]]["requirements"]
        )
        resume = (
            f"测试案例：{case['caseId']} {case['title']}；简历版本：{case['version']}\n"
            f"合成候选人：{case['caseId']} 测试同学（虚构，不对应真实个人）\n"
            f"求职方向：{case['title']}\n学习接触：{skills}\n"
            f"练习作品：{case['projectTitle']}\n配套项目文件：{case['projectFilename']}\n"
            f"材料范围及缺口：{case['boundary']}\n"
            "以上是合成自述；不能以简历自述代替源码或作品证据。\n"
        )
        (output / case["resumeFilename"]).write_text(resume, encoding="utf-8")
        with ZipFile(
            output / case["projectFilename"], "w", compression=ZIP_DEFLATED
        ) as bundle:
            for name, content in sorted(project_files(case).items()):
                info = ZipInfo(name, date_time=(2026, 9, 28, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                bundle.writestr(info, content)
        steps = (
            f"{case['caseId']}｜{case['title']}｜人工测试步骤 {case['version']}\n\n"
            "所有材料都是合成练习。ZIP 只上传，不在测试电脑执行其中脚本。\n"
            "1. 登录学生演示账号，打开“我的材料”。\n"
            "   初始化后已有同名材料可直接使用。若要测试重新上传，在材料名称末尾加本轮日期，避免重名。\n"
            f"2. 简历名称填写：{case['resumeName']}；选择：{case['resumeFilename']}。\n"
            f"3. 项目名称填写：{case['projectName']}；选择：{case['projectFilename']}。\n"
            "   项目说明填：合成静态测试作品，未执行，不代表本人贡献。材料角色选个人作品。\n"
            "4. 等两份材料均解析完成，预览内容，对照案例编号及文件名。\n"
            f"5. 岗位发现搜索并打开：{case['jobTitle']}。\n"
            "   选择 CareerProof 合成演示企业的同名岗位，不混用其他企业的要求。\n"
            f"6. 仅选择 {case['caseId']} 的对应简历与一个项目版本，不混入其他职业或历史难例。\n"
            "7. 负责人同意本次收费后，确认发送范围，点一次生成报告；不要连点重试。\n"
            f"8. 检查每条引用确实来自 {case['projectFilename']} 中的原文件。\n"
            f"9. 特别检查已知边界：{case['boundary']}\n"
            "   不能把计划说成完成、把静态代码说成运行成功，不能给无依据的高评级。\n"
            "10. 保存一条本人复核备注并刷新；记录通过/失败/未测及报告地址。\n"
            "    本人采纳不是独立认证；无需追求固定分数。\n"
            "11. 如测职业推荐，仍仅选择同一套材料。AI 推荐其他方向并不自动算失败，\n"
            "    应检查推荐理由与引用是否得到材料支持。生成职业规划会另外调用模型。\n"
        )
        (output / case["scriptFilename"]).write_text(steps, encoding="utf-8")
    (output / "catalog.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2), "utf-8"
    )
    return cases


if __name__ == "__main__":
    cases = build()
    (ROOT / "jianli/src/app/demo/samples.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(f"Built {len(cases)} paired role cases; no network or model calls.")
