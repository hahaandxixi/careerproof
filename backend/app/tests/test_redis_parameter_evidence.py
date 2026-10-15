"""Redis-typed injected parameters are evidence only at actual read/write calls."""
import pytest

from app.tools.code_analyzer import ProjectFileSnapshot, find_evidence


@pytest.mark.parametrize("declaration,annotation", [
    ("import redis", "redis.Redis"),
    ("import redis as store", "store.Redis"),
    ("from redis import Redis as Client", "Client"),
    ("from redis import StrictRedis", "StrictRedis"),
    ("import redis", "'redis.Redis'"),
])
def test_redis_typed_injected_client_points_to_actual_call(declaration, annotation):
    source = (
        f"{declaration}\ndef save(client: {annotation}, value: str):\n"
        "    client.setex('course:1', 60, value)\n    return client.get('course:1')\n"
    )
    evidence = find_evidence([ProjectFileSnapshot("cache_service.py", source)], "Redis")
    assert len(evidence) == 1
    assert evidence[0].evidence_type == "redis_usage"
    assert evidence[0].line_start == 3
    assert evidence[0].snippet == "client.setex('course:1', 60, value)"
    assert evidence[0].strength == "medium"


@pytest.mark.parametrize("source", [
    "import redis\ndef save(client):\n    return client.get('x')\n",
    "from other import Redis\ndef save(client: Redis):\n    return client.get('x')\n",
    "import redis\ndef save(client: redis.Redis):\n    return 1\n",
    "import redis\ndef save(client: redis.Redis):\n    client = {}\n    return client.get('x')\n",
    ("import redis\ndef first(client: redis.Redis):\n    return 1\n"
     "def second(client):\n    return client.get('x')\n"),
    ("import redis\ndef save(client: redis.Redis):\n    def nested(client):\n"
     "        return client.get('x')\n    return nested({})\n"),
    ("import redis\ndef outer(redis):\n    def nested(client: redis.Redis):\n"
     "        return client.get('x')\n    return nested({})\n"),
    "import redis\nredis = object()\ndef save(client: redis.Redis):\n    return client.get('x')\n",
    "import redis\ndef save(client: redis.Redis):\n    return 'client.get(\"x\")'\n",
    "import redis\ndef save(client: redis.Redis):\n    # client.get('x')\n    return 1\n",
    "import redis\ndef broken(client: redis.Redis):\n    return client.get(\n",
])
def test_unproven_or_shadowed_client_is_not_redis_implementation(source):
    assert find_evidence([ProjectFileSnapshot("service.py", source)], "Redis") == []


def test_detector_rule_version_invalidates_previous_report_cache(monkeypatch):
    from app.services import analysis

    snapshot = {"job": {}, "materials": [], "externalAiConsent": False}
    monkeypatch.setattr(analysis, "FORMULA_VERSION", "evidence-v3")
    previous = analysis._analysis_cache_key(snapshot)
    monkeypatch.setattr(analysis, "FORMULA_VERSION", "evidence-v4")
    assert analysis._analysis_cache_key(snapshot) != previous
