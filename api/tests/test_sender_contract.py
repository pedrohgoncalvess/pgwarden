"""Validate locally captured rows against the actual receiving API contract."""

import importlib.util
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet

from app.ingestion.catalog import validate_row
from app.ingestion.models import EventBatch


def test_all_sender_tables_match_receiver(tmp_path):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "http_sender", root / "collector/sender.py"
    )
    sender = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sender)
    path = tmp_path / "collector.sqlite3"
    with sqlite3.connect(path) as db:
        for migration in sorted((root / "migrations/sqlite").glob("*.sql")):
            if not migration.name.endswith(".rollback.sql"):
                db.executescript(migration.read_text())
    db = sender.connect(path)
    try:
        cipher = Fernet(Fernet.generate_key())
        sender.initialize(db, "http://localhost/events", "pgw_initial", cipher)
        for table in sender.ENTITIES + sender.METRICS:
            values = {}
            for column in db.execute(f'PRAGMA table_info("{table}")'):
                _, name, kind, required, default, primary = column
                if name == "id" or default is not None or not (required or primary):
                    continue
                if "INT" in kind or kind == "BOOLEAN":
                    values[name] = 1
                elif kind == "REAL":
                    values[name] = 1.5
                elif name.endswith("_at") or name in {
                    "backend_start",
                    "xact_start",
                    "query_start",
                    "state_change",
                }:
                    values[name] = "2026-11-01T00:00:00+00:00"
                else:
                    values[name] = "sample"
            columns = ",".join(f'"{name}"' for name in values)
            placeholders = ",".join("?" for _ in values)
            db.execute(
                f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})',
                tuple(values.values()),
            )
        db.commit()
        received = set()

        def receiver(url, key, body, timeout):
            batch = EventBatch.model_validate_json(body)
            for item in batch.events:
                validate_row(item.table, item.data)
                received.add(item.table)
            return {
                "acknowledged_event_ids": [str(item.event_id) for item in batch.events]
            }

        assert sender.deliver(db, cipher, 500, 5, receiver) == len(
            sender.ENTITIES + sender.METRICS
        )
        assert received == set(sender.ENTITIES + sender.METRICS)
    finally:
        db.close()
