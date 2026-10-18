import pytest
from fastapi.testclient import TestClient
from app import create_app

@pytest.fixture
def client():
    with TestClient(create_app()) as value:
        yield value

def test_book_available_slot(client):
    response = client.post("/bookings", json={"room": "A101", "hour": 10})
    assert response.status_code == 201
    assert response.json() == {"id": 1, "room": "A101", "hour": 10}

def test_duplicate_slot_is_rejected(client):
    payload = {"room": "A101", "hour": 10}
    assert client.post("/bookings", json=payload).status_code == 201
    response = client.post("/bookings", json=payload)
    assert response.status_code == 409
    assert response.json()["detail"] == "Slot already booked"

def test_invalid_hour_is_rejected(client):
    response = client.post("/bookings", json={"room": "A101", "hour": 24})
    assert response.status_code == 422
    assert any(x["loc"][-1] == "hour" for x in response.json()["detail"])
