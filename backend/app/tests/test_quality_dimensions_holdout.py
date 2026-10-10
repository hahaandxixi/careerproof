"""Codex-authored holdouts; no generated-model or human-semantic scores."""
import copy
import hashlib
from dataclasses import replace

from evals import run_quality_dimensions as runner

REQUIREMENT = {"title": "实现 FastAPI 健康检查接口", "skill": "FastAPI", "weight": 5}
OLD_SOURCE = (
    "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\n"
    "def health():\n    return {'ok': True}\n"
)


def contexts(content=OLD_SOURCE):
    return runner.build_contexts(
        'independent-stable-context', '使用 FastAPI 编写接口。', [REQUIREMENT],
        [{"path": "health.py", "content": content}],
    )


def comparison(provenance=False):
    # Keep IDs, requirements and grade invariant; change only source identity.
    base = copy.deepcopy(next(row for row in runner.load_cases()['changeCases']
                              if row['id'] == 'chg-no-change')['base'])
    target = copy.deepcopy(base)
    evidence = target['items'][0]['evidence'][0]
    if provenance:
        evidence['provenance'] = 'reference'
    else:
        evidence['snippet'] += '\n# independent material revision'
        evidence['contentHash'] = hashlib.sha256(evidence['snippet'].encode()).hexdigest()
    key = 'codex-holdout-stable-requirement'
    before = runner._view_ns(key, 'old', base)
    after = runner._view_ns(key, 'new', target)
    return runner.compare_views(
        before, after, runner._snapshot(key, base), runner._snapshot(key, target),
    )


def test_old_local_citation_id_acceptance_is_not_cross_version_source_proof():
    old, *_ = contexts()
    new, *_ = contexts(OLD_SOURCE.replace("True", "False"))
    ids = [[e.citation_id for e in context.evidence] for context in old]
    assert [c.requirement_id for c in old] == [c.requirement_id for c in new]
    assert ids == [[e.citation_id for e in context.evidence] for context in new]
    # This is an honest contract LIMITATION, not a claim of semantic success.
    assert runner.validate(new, runner.citation_analysis(old, ids))['accepted'] is True
    diff = comparison()
    assert 'requirements' not in diff.context_changes
    assert 'evidence' in diff.items[0].changes
    assert diff.items[0].added_evidence and diff.items[0].removed_evidence
    assert diff.items[0].base_level == diff.items[0].target_level


def test_same_hash_reference_role_change_is_detected_independently():
    diff = comparison(provenance=True)
    item = diff.items[0]
    assert 'evidence' in item.changes
    assert item.added_evidence[0].content_hash == item.removed_evidence[0].content_hash
    assert item.added_evidence[0].provenance == 'reference'
    assert item.removed_evidence[0].provenance == 'portfolio'


def test_vague_but_valid_plan_does_not_produce_an_operability_score():
    current, *_ = contexts()
    draft = {
        "deliverable": "进一步完善岗位材料", "steps": ["按要求补充相关资料", "持续优化具体工作"],
        "acceptanceChecks": ["材料符合岗位要求", "内容得到有效完善"],
    }
    assert runner.validate(current, runner.plan_analysis(current[0], draft))['accepted'] is True
    metrics = runner.evaluate(runner.load_cases())['metrics']['suggestion']
    assert metrics['generatedPlanOperabilityRate'] is None
    assert metrics['operabilityCounts'] is None


def test_exact_snippet_with_tampered_retrieval_hash_is_not_source_exact(monkeypatch):
    original = runner.enrich_evidence
    def tampered(*args, **kwargs):
        result = original(*args, **kwargs)
        first = result.items[0]
        evidence = replace(first.evidence_list[0], content_hash='f' * 64)
        changed = replace(first, evidence_list=[evidence, *first.evidence_list[1:]])
        return replace(result, items=[changed, *result.items[1:]])
    monkeypatch.setattr(runner, 'enrich_evidence', tampered)
    _, exact, count, _ = contexts()
    assert count > 0 and exact is False


def test_misclassified_citations_remain_in_metric_denominators():
    rows = copy.deepcopy(runner.evaluate(runner.load_cases())['results']['citation'])
    drafts = [draft for row in rows if row['sourceCheck'] != 'no-sources'
              for draft in row['drafts']]
    positive = next(d for d in drafts if d['expectedContractRejection'] is False)
    negative = next(d for d in drafts if d['expectedContractRejection'] is True)
    positive.update(accepted=False, expectationMatched=False)
    negative.update(accepted=True, expectationMatched=False)
    metrics = runner._citation_metrics(rows)
    assert metrics['validCitationGoldAccept'] == 2
    assert metrics['outOfBoundsGoldReject'] == 5
    assert metrics['contractCitationPrecision'] == 0.5
    assert metrics['contractCitationRecall'] == 0.5
    assert metrics['outOfBoundsRejectionRate'] == 0.8
    assert len(metrics['failures']) == 2
