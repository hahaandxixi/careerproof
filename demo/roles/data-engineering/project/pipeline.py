"""合成静态 ETL；未执行，不含调度或自动重试。"""

import csv
import sqlite3


def import_events(csv_path, database_path):
    with open(csv_path, encoding="utf-8", newline="") as source:
        rows = []
        for row in csv.DictReader(source):
            if not row["id"].strip() or not row["amount"].strip():
                raise ValueError("missing id or amount")
            amount = float(row["amount"])
            if amount < 0:
                raise ValueError("negative amount")
            rows.append((row["id"], amount))
    connection = sqlite3.connect(database_path)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, amount REAL NOT NULL)"
            )
            connection.executemany(
                "INSERT INTO events(id, amount) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET amount=excluded.amount",
                rows,
            )
    finally:
        connection.close()
