PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    capacity INTEGER NOT NULL CHECK(capacity > 0),
    remaining INTEGER NOT NULL CHECK(remaining >= 0 AND remaining <= capacity)
);
CREATE TABLE IF NOT EXISTS registrations (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id),
    student_code TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'cancelled')),
    UNIQUE(event_id, student_code)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    registration_id INTEGER NOT NULL REFERENCES registrations(id),
    action TEXT NOT NULL CHECK(action IN ('register', 'cancel'))
);
