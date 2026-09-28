from evals.retire_legacy_materials import is_legacy


def test_legacy_retirement_requires_both_known_name_and_synthetic_file():
    assert is_legacy("resume", "Function Calling 合成简历 20260918-152713", ["student-resume.txt"])
    assert is_legacy("project", "历史完整报告 injected-history 20260927", ["synthetic-history.zip"])
    assert is_legacy("project", "视觉合成验收 20260926-224539", ["synthetic-vision-panel.png"])
    assert is_legacy(
        "project", "Function Calling 合成项目 20260925", ["evidence-function-call.zip"]
    )
    assert not is_legacy("resume", "测试1", ["张振鑫简历.docx"])
    assert not is_legacy("resume", "AI完整报告合成简历20260917", ["真实简历.docx"])
    assert not is_legacy("project", "CP08｜任务数据库管理｜测试项目", ["synthetic-history.zip"])
    assert not is_legacy("resume", "Function Calling 合成简历 20260918", [])
    assert not is_legacy("project", "我的项目", ["project.zip"])
