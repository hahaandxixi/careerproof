"""合成测试用例（新版）：与 process_records 具名实现对应。"""
from pipeline import process_records


def test_process_records_totals():
    records = [
        {"category": "图书", "amount": "12.5"},
        {"category": "图书", "amount": "30"},
        {"category": "文具", "amount": "8"},
    ]
    result = process_records(records)
    assert result["图书"] == 42.5
    assert result["文具"] == 8


def test_process_records_empty_category():
    records = [{"amount": "5"}]
    assert process_records(records) == {"未分类": 5.0}
