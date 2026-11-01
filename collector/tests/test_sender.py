"""Exercise durable capture, delivery retries and real HTTP serialization."""

import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from uuid import UUID

import pytest
from cryptography.fernet import Fernet

from sender import connect, deliver, initialize


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def local(tmp_path):
    path = tmp_path / "collector.sqlite3"
    with sqlite3.connect(path) as db:
        for migration in sorted((ROOT / "migrations/sqlite").glob("*.sql")):
            if not migration.name.endswith(".rollback.sql"):
                db.executescript(migration.read_text())
    db = connect(path)
    cipher = Fernet(Fernet.generate_key())
    yield db, cipher, path
    db.close()


def seed(db):
    db.execute(
        """INSERT INTO collector_server(name,host,port,username,password)
        VALUES('production','secret-host','5432','secret-user','secret-password')"""
    )
    db.execute("INSERT INTO metadata_database(server_id,db_name) VALUES(1,'app')")
    db.execute(
        "INSERT INTO metadata_table(oid,database_id,schema_name,name) VALUES(10,1,'public','items')"
    )
    db.execute(
        """INSERT INTO metadata_column(table_id,name,data_type,ordinal_position)
        VALUES(1,'id','integer',1)"""
    )
    db.execute("UPDATE metadata_column SET fk_table_id=1,fk_column_id=1 WHERE id=1")
    db.commit()


def test_capture_transaction_rollback_and_credential_filter(local):
    db, cipher, _ = local
    initialize(db, "http://localhost/v1/ingestion/events", "pgw_initial", cipher)
    seed(db)
    rows = db.execute("SELECT * FROM sender_outbox ORDER BY seq").fetchall()
    assert [row["table_name"] for row in rows[:3]] == [
        "collector_server",
        "metadata_database",
        "metadata_table",
    ]
    assert "secret-" not in "".join(row["data"] for row in rows)
    assert len({row["event_id"] for row in rows}) == len(rows)
    assert all(UUID(row["event_id"]) for row in rows)
    assert [row["occurred_us"] for row in rows] == sorted(
        {row["occurred_us"] for row in rows}
    )
    before = len(rows)
    db.execute(
        "INSERT INTO metric_cpu(collected_at,server_id,cpu_percent,cpu_count) VALUES('2026-11-01T00:00:00Z',1,12.5,4)"
    )
    db.rollback()
    assert db.execute("SELECT count(*) FROM sender_outbox").fetchone()[0] == before


def test_backfill_fk_cycles_and_restart_identity(local):
    db, cipher, path = local
    seed(db)
    initialize(db, "http://localhost/events", "pgw_initial", cipher)
    columns = [
        json.loads(row[0])
        for row in db.execute(
            "SELECT data FROM sender_outbox WHERE table_name='metadata_column' ORDER BY seq"
        )
    ]
    assert columns[0]["fk_column_id"] is None
    assert columns[1]["fk_column_id"] == 1
    before = tuple(
        db.execute("SELECT source_id,project_key FROM sender_state").fetchone()
    )
    with connect(path) as restarted:
        initialize(
            restarted, "http://localhost/events", "pgw_stale_environment", cipher
        )
        assert (
            tuple(
                restarted.execute(
                    "SELECT source_id,project_key FROM sender_state"
                ).fetchone()
            )
            == before
        )
        with pytest.raises(ValueError, match="destination"):
            initialize(restarted, "http://another/events", "pgw_other", cipher)


def test_retry_same_payload_rotation_and_ack_atomicity(local):
    db, cipher, _ = local
    initialize(db, "http://localhost/events", "pgw_initial", cipher)
    seed(db)
    bodies = []

    def lost_response(url, key, body, timeout):
        bodies.append(body)
        raise TimeoutError()

    with pytest.raises(TimeoutError):
        deliver(db, cipher, 500, 1, lost_response)

    def successful_retry(url, key, body, timeout):
        assert body == bodies[0]
        assert key == "pgw_initial"
        events = json.loads(body)["events"]
        return {
            "acknowledged_event_ids": [item["event_id"] for item in events],
            "replacement_key": "pgw_rotated",
        }

    count = deliver(db, cipher, 500, 1, successful_retry)
    assert count > 0
    assert db.execute("SELECT count(*) FROM sender_outbox").fetchone()[0] == 0
    assert (
        cipher.decrypt(db.execute("SELECT project_key FROM sender_state").fetchone()[0])
        == b"pgw_rotated"
    )
    initialize(db, "http://localhost/events", "pgw_initial", cipher)
    assert (
        cipher.decrypt(db.execute("SELECT project_key FROM sender_state").fetchone()[0])
        == b"pgw_rotated"
    )
    initialize(db, "http://localhost/events", "pgw_recovered", cipher, set_key=True)
    assert (
        cipher.decrypt(db.execute("SELECT project_key FROM sender_state").fetchone()[0])
        == b"pgw_recovered"
    )


def test_reject_partial_ack_and_capture_relationship_delete(local):
    db, cipher, _ = local
    initialize(db, "http://localhost/events", "pgw_initial", cipher)
    seed(db)
    before = db.execute("SELECT count(*) FROM sender_outbox").fetchone()[0]
    with pytest.raises(ValueError, match="acknowledgement"):
        deliver(db, cipher, 2, 1, lambda *args: {"acknowledged_event_ids": []})
    assert db.execute("SELECT count(*) FROM sender_outbox").fetchone()[0] == before
    db.execute(
        """INSERT INTO metadata_index(database_id,table_id,oid,name,type,definition)
        VALUES(1,1,11,'items_idx','btree','CREATE INDEX items_idx ON items(id)')"""
    )
    db.execute("INSERT INTO metadata_index_column VALUES(1,1,1)")
    db.execute("DELETE FROM metadata_index_column WHERE index_id=1")
    db.commit()
    assert (
        db.execute(
            "SELECT operation FROM sender_outbox ORDER BY seq DESC LIMIT 1"
        ).fetchone()[0]
        == "delete"
    )


def test_http_transport_headers_body_and_real_ack(local):
    db, cipher, _ = local
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, self.headers["Authorization"], payload))
            body = json.dumps(
                {
                    "acknowledged_event_ids": [
                        event["event_id"] for event in payload["events"]
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        initialize(
            db,
            f"http://127.0.0.1:{server.server_port}/v1/ingestion/events",
            "pgw_initial",
            cipher,
        )
        seed(db)
        assert deliver(db, cipher, 2, 5) == 2
        assert requests[0][0] == "/v1/ingestion/events"
        assert requests[0][1] == "Bearer pgw_initial"
        assert len(requests[0][2]["events"]) == 2
    finally:
        server.shutdown()
        worker.join()
        server.server_close()


def test_failed_local_ack_rolls_back_replacement_key(local):
    db, cipher, _ = local
    initialize(db, "http://localhost/events", "pgw_initial", cipher)
    seed(db)
    db.execute(
        """CREATE TRIGGER fail_ack BEFORE DELETE ON sender_outbox
        BEGIN SELECT RAISE(ABORT, 'disk failure'); END"""
    )
    db.commit()

    def response(url, key, body, timeout):
        return {
            "acknowledged_event_ids": [
                event["event_id"] for event in json.loads(body)["events"]
            ],
            "replacement_key": "pgw_rotated",
        }

    with pytest.raises(sqlite3.IntegrityError):
        deliver(db, cipher, 500, 1, response)
    assert db.execute("SELECT count(*) FROM sender_outbox").fetchone()[0] > 0
    assert (
        cipher.decrypt(db.execute("SELECT project_key FROM sender_state").fetchone()[0])
        == b"pgw_initial"
    )
