"""Freeze once before CareerProof sees the original demo; rubric stays outside ZIP."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).parent
PROJECT = ROOT / "demo/complete-projects/campus-signup-v1"
OUT = ROOT / "output/demo"
OUT.mkdir(parents=True, exist_ok=True)
sha = lambda data: hashlib.sha256(data).hexdigest()
files = sorted(p for p in PROJECT.rglob("*") if p.is_file()
               and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts)
assert len(files) == 9
archive_path = OUT / "CareerProof-campus-signup-v1.zip"
with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
    for file in files:
        info = zipfile.ZipInfo(file.relative_to(PROJECT).as_posix(), (2026, 10, 21, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, file.read_bytes())
resume = OUT / "CareerProof-campus-signup-resume.txt"
assert not resume.exists()
resume.write_text("合成学生：林舟（虚构）。提供校园活动报名项目，使用Python、FastAPI、SQLite SQL、pytest。"
                  "材料涉及活动创建、报名、取消及持久化；人物与经历均虚构，不声称商业上线或个人贡献已获认证。\n",
                  encoding="utf-8")
manifest = {
    "version": "campus-signup-v1", "frozenBeforeCareerProofUpload": True,
    "zip": str(archive_path), "zipSha256": sha(archive_path.read_bytes()),
    "resume": str(resume), "resumeSha256": sha(resume.read_bytes()),
    "files": {p.relative_to(PROJECT).as_posix(): sha(p.read_bytes()) for p in files},
    "excluded": ["evaluation criteria", "expected answers", "runtime outputs", "database", "cache", "virtualenv"],
    "sourceChangedAfterReadingReport": False,
}
(EVIDENCE / "material-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
criteria = [
    {"key": "api", "skill": "FastAPI", "requirement": "实现校园活动创建、报名、取消和查询接口，校验请求并返回对应错误状态",
     "source": ["campus_signup/api.py"],
     "observe": ["真实路由调用RegistrationService", "Pydantic输入约束", "领域异常和数据库异常转HTTP响应"],
     "notProven": ["已部署到公网", "已认证用户身份"]},
    {"key": "sql", "skill": "SQL", "requirement": "使用SQLite SQL持久化活动与报名，参数化读写，写入失败回滚名额及报名记录",
     "source": ["campus_signup/storage.py", "campus_signup/service.py", "campus_signup/schema.sql"],
     "observe": ["SQLite实际连接及SQL执行", "BEGIN/commit/rollback事务边界", "名额、报名及审计同事务", "重启读取真实保存行"],
     "notProven": ["PostgreSQL/MySQL连接", "多机分布式事务"]},
    {"key": "business", "skill": "Python", "requirement": "用Python完成满额与重复报名拒绝，取消后恢复一个名额，避免重复取消导致名额增加",
     "source": ["campus_signup/service.py"],
     "observe": ["register完整输入/业务检查/写入/返回", "cancel状态检查/恢复名额/写审计"],
     "notProven": ["任意Python函数即证明以上业务完整"]},
    {"key": "tests", "skill": "pytest", "requirement": "编写行为测试验证成功报名、重复与满额拒绝、取消、事务回滚、重启恢复及最后名额竞争",
     "source": ["tests/test_registration.py"],
     "observe": ["实际请求及状态/持久化结果断言", "故障触发器与回滚数据断言", "两个线程竞争及一胜一负断言"],
     "notProven": ["测试源码存在等于已经通过", "测试夹具描述等于断言"]},
    {"key": "redis", "skill": "Redis", "requirement": "使用Redis缓存活动查询并在报名或取消后失效缓存",
     "source": [], "observe": ["材料没有Redis连接、缓存写入或失效实现"],
     "notProven": ["函数名或简历技能可替代缓存实现"]},
]
plan = {"basis": "After actual business execution and material freeze, before CareerProof upload/results; implementation facts, no target grades.",
        "requirements": criteria,
        "checking": ["Check every citation against exact file bytes/line interval", "Separate indexed files from selected evidence",
                     "Record missing business facts without altering material", "Rules result is not AI semantic validation"],
        "independentHumanReview": False, "realModelRequestsAllowed": False}
(EVIDENCE / "evaluation-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Frozen", len(files), "files:", manifest["zipSha256"])
