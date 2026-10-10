"""Independent evidence-integrity probes, owned by Codex rather than ZCode28."""
import copy
import hashlib
import json

import pytest

from evals import run_quality_review_benchmark as benchmark


@pytest.mark.parametrize('target', ['review', 'input'])
def test_ambiguous_duplicate_json_keys_cannot_produce_a_valid_replay(tmp_path, target):
    original_input = benchmark.DEFAULT_INPUT.read_bytes()
    review = json.loads(benchmark.DEFAULT_REVIEW.read_text(encoding='utf-8'))
    input_bytes = original_input
    if target == 'input':
        text = original_input.decode('utf-8')
        marker = '"id": "37882b616f"'
        assert marker in text
        input_bytes = text.replace(marker, '"id": "hidden-case", ' + marker, 1).encode()
        review['inputSha256'] = hashlib.sha256(input_bytes).hexdigest()
    review_text = json.dumps(review, ensure_ascii=False)
    if target == 'review':
        marker = '"sourceCompliance": 2'
        assert marker in review_text
        review_text = review_text.replace(marker, '"sourceCompliance": 0, ' + marker, 1)
    input_path, review_path = tmp_path / 'input.json', tmp_path / 'review.json'
    input_path.write_bytes(input_bytes)
    review_path.write_text(review_text, encoding='utf-8')
    output = tmp_path / 'result.json'
    assert benchmark.main(argv=['--input', str(input_path), '--review', str(review_path),
                                '--output', str(output)]) == 1
    assert not output.exists()


def test_unknown_source_quality_cannot_be_rescued_by_other_perfect_scores():
    raw = benchmark.DEFAULT_INPUT.read_bytes()
    payload = json.loads(raw)
    review = copy.deepcopy(json.loads(benchmark.DEFAULT_REVIEW.read_text(encoding='utf-8')))
    row = next(case for case in review['cases'] if case['caseId'] == '37882b616f')
    row['scores']['sourceCompliance'] = None
    row['evidence']['sourceCompliance'] = ''
    rows, _, dims = benchmark.validate_blind_review(payload, review, raw)
    metrics = benchmark.replay_metrics(rows, dims)
    assert metrics['sampleDenominator'] == 8
    assert metrics['strictPass']['count'] == 2
    assert metrics['strictPass']['rate'] == 0.25
    assert '37882b616f' in metrics['unscored']['caseIds']
    assert '37882b616f' not in metrics['strictPass']['caseIds']


def test_input_rubric_cannot_remove_an_unfavorable_required_dimension():
    payload = json.loads(benchmark.DEFAULT_INPUT.read_bytes())
    review = copy.deepcopy(json.loads(benchmark.DEFAULT_REVIEW.read_text(encoding='utf-8')))
    del payload['rubric']['stepsExecutable']
    raw = json.dumps(payload, ensure_ascii=False).encode()
    review['inputSha256'] = hashlib.sha256(raw).hexdigest()
    for row in review['cases']:
        del row['scores']['stepsExecutable']
        del row['evidence']['stepsExecutable']
    with pytest.raises(ValueError):
        benchmark.validate_blind_review(payload, review, raw)
