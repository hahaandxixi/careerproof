import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from campus_signup.api import create_app
from campus_signup.service import RegistrationError, RegistrationService
from campus_signup.storage import Store


@pytest.fixture
def database(tmp_path):
    return tmp_path / "signup.sqlite3"


def event(client, capacity=2):
    response = client.post("/events", json={"title": "Campus workshop", "capacity": capacity})
    assert response.status_code == 201
    return response.json()["id"]


def signup(client, event_id, student="S001"):
    return client.post("/registrations", json={"event_id": event_id, "student_code": student})


def test_registration_persists_across_application_restart(database):
    with TestClient(create_app(database)) as client:
        event_id = event(client)
        registered = signup(client, event_id)
        assert registered.status_code == 201
        saved = registered.json()
        assert saved["status"] == "active"
        assert client.get("/events").json()[0]["remaining"] == 1
    with TestClient(create_app(database)) as restarted:
        assert restarted.get("/registrations").json() == [saved]
        assert restarted.get("/events").json()[0]["remaining"] == 1


def test_duplicate_does_not_consume_another_place(database):
    with TestClient(create_app(database)) as client:
        event_id = event(client)
        assert signup(client, event_id).status_code == 201
        response = signup(client, event_id)
        assert response.status_code == 409
        assert response.json()["detail"] == "Registration already exists"
        assert len(client.get("/registrations").json()) == 1
        assert client.get("/events").json()[0]["remaining"] == 1


def test_full_event_rejects_without_a_registration(database):
    with TestClient(create_app(database)) as client:
        event_id = event(client, capacity=1)
        assert signup(client, event_id).status_code == 201
        response = signup(client, event_id, "S002")
        assert response.status_code == 409
        assert response.json()["detail"] == "Event full"
        assert len(client.get("/registrations").json()) == 1


def test_unknown_event_is_404(database):
    with TestClient(create_app(database)) as client:
        assert signup(client, 123).status_code == 404
        assert client.get("/registrations").json() == []


@pytest.mark.parametrize("payload", [
    {"event_id": 0, "student_code": "S001"},
    {"event_id": 1, "student_code": "X"},
])
def test_invalid_signup_is_422(database, payload):
    with TestClient(create_app(database)) as client:
        assert client.post("/registrations", json=payload).status_code == 422
        assert client.get("/registrations").json() == []


def test_cancel_restores_place_once(database):
    with TestClient(create_app(database)) as client:
        event_id = event(client, capacity=1)
        registration_id = signup(client, event_id).json()["id"]
        response = client.post(f"/registrations/{registration_id}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        assert client.get("/events").json()[0]["remaining"] == 1
        assert client.post(f"/registrations/{registration_id}/cancel").status_code == 409
        assert client.get("/events").json()[0]["remaining"] == 1
        assert signup(client, event_id, "S002").status_code == 201


def test_failed_audit_insert_rolls_back_registration_and_capacity(database):
    store = Store(database)
    store.initialize()
    service = RegistrationService(store)
    event_id = service.create_event("Rollback workshop", 1)["id"]
    with closing(store.connect()) as connection:
        connection.execute("""CREATE TRIGGER fail_audit BEFORE INSERT ON audit_log
            BEGIN SELECT RAISE(ABORT, 'audit write rejected'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="audit write rejected"):
        service.register(event_id, "S001")
    assert store.list_registrations() == []
    assert store.list_events()[0]["remaining"] == 1
    with closing(store.connect()) as connection:
        assert connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_database_failure_becomes_503_without_partial_write(database):
    with TestClient(create_app(database), raise_server_exceptions=False) as client:
        event_id = event(client, capacity=1)
        with sqlite3.connect(database) as connection:
            connection.execute("""CREATE TRIGGER fail_audit BEFORE INSERT ON audit_log
                BEGIN SELECT RAISE(ABORT, 'audit write rejected'); END""")
        response = signup(client, event_id)
        assert response.status_code == 503
        assert response.json() == {"detail": "Storage unavailable"}
        assert client.get("/registrations").json() == []
        assert client.get("/events").json()[0]["remaining"] == 1


def test_last_place_has_one_winner_under_two_writers(database):
    store = Store(database)
    store.initialize()
    service = RegistrationService(store)
    event_id = service.create_event("Last place", 1)["id"]
    barrier = Barrier(2)

    def attempt(student):
        barrier.wait(timeout=5)
        try:
            return service.register(event_id, student)["status"]
        except RegistrationError as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["S001", "S002"]))
    assert sorted(map(str, results)) == ["409", "active"]
    assert len(store.list_registrations()) == 1
    assert store.list_events()[0]["remaining"] == 0


def test_student_value_is_bound_as_data(database):
    student = "x'); DROP TABLE events;--"
    with TestClient(create_app(database)) as client:
        event_id = event(client)
        response = signup(client, event_id, student)
        assert response.status_code == 201
        assert response.json()["student_code"] == student
        assert client.get("/events").json()[0]["remaining"] == 1
