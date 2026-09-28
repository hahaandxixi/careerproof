"""合成测试设计，未执行；服务由测试者注入，不提供通过率。"""


def test_empty_title(client):
    response = client.post("/tasks", json={"title": ""})
    assert response.status_code == 422


def test_create_task(client):
    response = client.post("/tasks", json={"title": "demo"})
    assert response.status_code == 201
    assert response.json()["title"] == "demo"
