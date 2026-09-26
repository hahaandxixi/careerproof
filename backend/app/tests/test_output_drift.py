import pytest

from evals.check_output_drift import compare, main


def test_wording_only_change_is_not_rating_drift():
    baseline = {"results": [{"id": "synthetic", "accepted": True,
                             "analysis": {"summary": "old", "items": []}}]}
    current = {"results": [{"id": "synthetic", "accepted": True,
                            "analysis": {"summary": "new", "items": []}}]}
    diff = compare(baseline, current)[0]
    assert diff["status"] == "unchanged" and diff["wordingChanged"] is True


def test_failure_and_missing_case_are_preserved():
    baseline = {"results": [{"id": "synthetic", "accepted": True}, {"id": "not-run"}]}
    current = {"results": [{"id": "synthetic", "accepted": False, "httpStatus": 429}]}
    result = {row["id"]: row for row in compare(baseline, current)}
    assert result["synthetic"]["signalChanges"] == ["accepted", "httpStatus"]
    assert result["not-run"]["status"] == "not_run"


async def test_live_without_paid_flag_exits_before_loading_files(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["drift", "--baseline", "not-read.json", "--output",
                                     str(tmp_path / "new.json"), "--live"])
    with pytest.raises(SystemExit) as error:
        await main()
    assert error.value.code == 2 and not (tmp_path / "new.json").exists()
