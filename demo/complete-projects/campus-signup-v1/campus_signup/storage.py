import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        self.path = path

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as connection:
            connection.executescript(Path(__file__).with_name("schema.sql").read_text())

    @contextmanager
    def transaction(self):
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_events(self):
        with closing(self.connect()) as connection:
            return [dict(row) for row in connection.execute(
                "SELECT id, title, capacity, remaining FROM events ORDER BY id"
            )]

    def list_registrations(self):
        with closing(self.connect()) as connection:
            return [dict(row) for row in connection.execute(
                "SELECT id, event_id, student_code, status FROM registrations ORDER BY id"
            )]
