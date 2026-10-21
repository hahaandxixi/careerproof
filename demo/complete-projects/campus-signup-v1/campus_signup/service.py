from .storage import Store


class RegistrationError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class RegistrationService:
    def __init__(self, store: Store):
        self.store = store

    def create_event(self, title: str, capacity: int):
        if not title.strip() or capacity < 1:
            raise RegistrationError("Invalid event", 422)
        with self.store.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO events(title, capacity, remaining) VALUES (?, ?, ?)",
                (title.strip(), capacity, capacity),
            )
            return {"id": cursor.lastrowid, "title": title.strip(),
                    "capacity": capacity, "remaining": capacity}

    def register(self, event_id: int, student_code: str):
        with self.store.transaction() as connection:
            event = connection.execute(
                "SELECT id, remaining FROM events WHERE id = ?", (event_id,)
            ).fetchone()
            if event is None:
                raise RegistrationError("Event not found", 404)
            previous = connection.execute(
                "SELECT id FROM registrations WHERE event_id = ? AND student_code = ?",
                (event_id, student_code),
            ).fetchone()
            if previous is not None:
                raise RegistrationError("Registration already exists", 409)
            updated = connection.execute(
                "UPDATE events SET remaining = remaining - 1 WHERE id = ? AND remaining > 0",
                (event_id,),
            )
            if updated.rowcount != 1:
                raise RegistrationError("Event full", 409)
            cursor = connection.execute(
                "INSERT INTO registrations(event_id, student_code, status) VALUES (?, ?, 'active')",
                (event_id, student_code),
            )
            registration_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO audit_log(registration_id, action) VALUES (?, 'register')",
                (registration_id,),
            )
            return {"id": registration_id, "event_id": event_id,
                    "student_code": student_code, "status": "active"}

    def cancel(self, registration_id: int):
        with self.store.transaction() as connection:
            row = connection.execute(
                "SELECT event_id, student_code, status FROM registrations WHERE id = ?",
                (registration_id,),
            ).fetchone()
            if row is None:
                raise RegistrationError("Registration not found", 404)
            if row["status"] != "active":
                raise RegistrationError("Registration already cancelled", 409)
            connection.execute(
                "UPDATE registrations SET status = 'cancelled' WHERE id = ?", (registration_id,)
            )
            connection.execute(
                "UPDATE events SET remaining = remaining + 1 WHERE id = ?", (row["event_id"],)
            )
            connection.execute(
                "INSERT INTO audit_log(registration_id, action) VALUES (?, 'cancel')",
                (registration_id,),
            )
            return {"id": registration_id, "event_id": row["event_id"],
                    "student_code": row["student_code"], "status": "cancelled"}
