"""Keep replay evidence intact while removing duplicated statement payloads."""

import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql


def test_receipt_cleanup_preserves_ids_fingerprints_and_other_metrics(monkeypatch):
    dsn = os.getenv("PGWARDEN_ANALYTICS_TEST_DSN")
    if not dsn:
        pytest.skip("Set PGWARDEN_ANALYTICS_TEST_DSN to a development server")
    name = "receipt_pruning_" + uuid4().hex[:12]
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    options = psycopg.conninfo.conninfo_to_dict(dsn) | {"dbname": name}
    try:
        with psycopg.connect(**options) as connection:
            connection.execute("""CREATE SCHEMA ingestion;
                CREATE TABLE ingestion.project(id UUID PRIMARY KEY);
                CREATE TABLE ingestion.event(project_id UUID,source_id UUID,event_id UUID,
                    received_at TIMESTAMPTZ,table_name TEXT,payload JSONB NOT NULL,fingerprint TEXT,
                    PRIMARY KEY(project_id,source_id,event_id));
                CREATE INDEX ingestion_event_received ON ingestion.event(project_id,received_at DESC);
            """)
            projects = [uuid4(),uuid4()]
            for project in projects:
                connection.execute("INSERT INTO ingestion.project VALUES(%s)",(project,))
            now = datetime.now(timezone.utc)
            for index in range(6):
                connection.execute("INSERT INTO ingestion.event VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (projects[index % 2],uuid4(),uuid4(),now,
                     "metric_ram" if index == 5 else "metric_query_workload",
                     '{}' if index == 4 else '{"sample":"preserve fingerprint only"}', str(index)))
            before = connection.execute("SELECT project_id,source_id,event_id,fingerprint FROM ingestion.event ORDER BY fingerprint").fetchall()
        for field, value in options.items():
            variable = {"dbname":"DB_NAME","host":"DB_HOST","port":"DB_PORT","user":"DB_USER","password":"DB_PASSWORD"}.get(field)
            if variable:
                monkeypatch.setenv(variable,value)
        root = Path(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location("prune_receipts",root/"migrations/prune_statement_receipts.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.prune_receipts(batch_size=2) == 4
        with psycopg.connect(**options) as connection:
            assert connection.execute("SELECT project_id,source_id,event_id,fingerprint FROM ingestion.event ORDER BY fingerprint").fetchall() == before
            assert connection.execute("SELECT count(*) FROM ingestion.event WHERE table_name='metric_query_workload' AND payload<>'{}'::jsonb").fetchone()[0] == 0
            assert connection.execute("SELECT payload FROM ingestion.event WHERE table_name='metric_ram'").fetchone()[0] != {}
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
