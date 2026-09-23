"""Small fixed recall/safety probe for the optional local document retriever."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.core.config import settings
from app.services.matching_materials import MatchMaterials, analyze_materials
from app.services.task_runner import run_isolated
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.matcher import RequirementInput
from app.tools.semantic_retrieval import (
    MODEL_REVISION,
    VERSION,
    load_local_model,
    retrieve_semantic_candidates,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    model = load_local_model(settings.semantic_model_cache_dir)
    cases = [
        (
            "database_paraphrase",
            RequirementInput(uuid4(), "支持数据库事务，失败后回滚并保证一致性", "事务一致性", 5),
            ProjectFileSnapshot(
                "project/transactions.md",
                "订单写入失败时撤销库存扣减，两个变更要么一起成功，要么都不生效。\n",
            ),
            True,
        ),
        (
            "test_paraphrase",
            RequirementInput(uuid4(), "具备接口自动化测试与响应校验经验", "接口测试", 5),
            ProjectFileSnapshot(
                "project/testing.md",
                "每次提交代码都自动请求下单接口，并检查返回状态和订单字段是否符合预期。\n",
            ),
            True,
        ),
        (
            "deployment_paraphrase",
            RequirementInput(uuid4(), "具备容器部署和服务健康检查经验", "容器运维", 5),
            ProjectFileSnapshot(
                "project/deployment.md",
                "发布流水线将应用镜像上线后，定期探测服务状态，异常时阻止流量进入。\n",
            ),
            True,
        ),
        (
            "unrelated_document",
            RequirementInput(uuid4(), "具备容器部署和服务健康检查经验", "容器运维", 5),
            ProjectFileSnapshot(
                "project/marketing.md",
                "本项目负责市场活动策划、社群内容维护和线下品牌宣传。\n",
            ),
            False,
        ),
    ]
    records = []
    for name, requirement, file, expected in cases:
        hits, windows = retrieve_semantic_candidates([requirement], [file], model)
        actual = bool(hits.get(requirement.id))
        records.append(
            {"case": name, "expectedHit": expected, "actualHit": actual, "windows": windows}
        )
    with TemporaryDirectory() as temporary:
        content = cases[0][2].content.encode("utf-8")
        Path(temporary, "source.md").write_bytes(content)
        materials = MatchMaterials(
            resume_text="合成测试学生",
            files=[
                {
                    "storageKey": "source.md",
                    "hash": hashlib.sha256(content).hexdigest(),
                    "path": cases[0][2].path,
                }
            ],
            snapshots=[],
        )
        result = asyncio.run(
            run_isolated(analyze_materials, [cases[0][1]], materials, Path(temporary))
        )
        source = result.items[0].evidence_list[0]
        complete = (
            source.evidence_type == "semantic_document_candidate"
            and source.snippet.strip() == cases[0][2].content.strip()
            and result.items[0].rule_base_score == 0
            and result.retrieval_steps[-1]["status"] == "active"
        )
        records.append(
            {"case": "isolated_full_retrieval", "expectedHit": True, "actualHit": complete}
        )
    output = {
        "engine": VERSION,
        "modelRevision": MODEL_REVISION,
        "scope": "fixed synthetic retrieval wiring, not general semantic accuracy",
        "cases": records,
    }
    serialized = json.dumps(output, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        with args.output.open("x", encoding="utf-8") as result_file:
            result_file.write(serialized + "\n")
    if any(record["expectedHit"] != record["actualHit"] for record in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
