import httpx
import pytest

from evals.seed_e2e import IsolationError, _fixture_page


def response(data):
    return httpx.Response(
        200, json={"code": 0, "data": data}, request=httpx.Request("GET", "http://test")
    )


def test_isolated_seed_accepts_the_complete_paginated_fixture():
    assert _fixture_page(response({"items": [{"id": "a"}], "page": 1, "total": 1})) == [
        {"id": "a"}
    ]


@pytest.mark.parametrize(
    "data",
    [[], {"items": [], "page": 2, "total": 0}, {"items": [], "page": 1, "total": 21}],
)
def test_isolated_seed_rejects_legacy_or_partial_pages(data):
    with pytest.raises(IsolationError, match="complete first-page"):
        _fixture_page(response(data))
