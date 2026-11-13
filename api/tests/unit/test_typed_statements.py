"""Verify typed ingestion and historical conversion without application data."""

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from app.ingestion.catalog import validate_row

ROOT = Path(__file__).resolve().parents[3]


def _event(**changes):
    return {
        "database_id": 1, "collected_at": "2026-11-12T10:00:00Z",
        "query_id": 123, "user_id": 10, "is_toplevel": True,
        "calls": 10, "total_exec_time": 30, "shared_blks_read": 2,
        "shared_blks_hit": 9, "dealloc": 0, "query": "SELECT $1",
        **changes,
    }


def test_legacy_events_are_converted_without_overwriting_identity():
    row = validate_row("metric_query_workload", _event(statement_data=json.dumps({
        "queryid": 999, "calls": 900, "rows": 30,
        "wal_bytes": 18446744073709551615, "stats_since": "2026-11-12T00:00:00Z",
    })))
    assert row["query_id"] == 123 and row["calls"] == 10
    assert row["wal_bytes"] == Decimal("18446744073709551615")
    assert row["stats_since"].tzinfo is not None
    assert "statement_data" not in row


def test_typed_fields_keep_precision_and_optional_version_columns():
    row = validate_row("metric_query_workload", _event(wal_bytes="18446744073709551615"))
    assert row["wal_bytes"] == Decimal("18446744073709551615")
    assert "stats_since" not in row
    assert "jit_deform_time" not in row


def test_service_field_catalogs_remain_equal():
    source = (ROOT / "collector/database/statement_fields.py").read_text()
    for package in ("api", "analytics"):
        assert (ROOT / package / "database/models/metric/statement_fields.py").read_text() == source


def test_unknown_legacy_fields_are_rejected_instead_of_discarded():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        validate_row("metric_query_workload", _event(statement_data='{"future_counter":5}'))


@pytest.mark.parametrize("payload", ["[]", "null", "1", "invalid"])
def test_legacy_non_object_payloads_are_rejected(payload):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        validate_row("metric_query_workload", _event(statement_data=payload))
    assert error.value.status_code == 422


def test_postgres_migration_preserves_typed_history_and_deduplicates_text():
    dsn = os.getenv("PGWARDEN_ANALYTICS_TEST_DSN")
    if not dsn:
        pytest.skip("Set PGWARDEN_ANALYTICS_TEST_DSN to a development PostgreSQL server")
    name = "typed_migration_" + uuid4().hex[:12]
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        options = psycopg.conninfo.conninfo_to_dict(dsn) | {"dbname": name}
        with psycopg.connect(**options) as connection:
            connection.execute("CREATE SCHEMA metadata; CREATE SCHEMA metric; CREATE TABLE metadata.database(id BIGINT PRIMARY KEY); INSERT INTO metadata.database VALUES(1)")
            initial = (ROOT / "migrations/sql/20261031_02_index-advisor.sql").read_text()
            connection.execute(initial[initial.index("CREATE TABLE metric.query_workload"):])
            connection.execute("ALTER TABLE metric.query_workload ADD COLUMN query TEXT, ADD COLUMN query_hash TEXT, ADD COLUMN user_name TEXT, ADD COLUMN statement_data TEXT")
            for minute in (0, 1):
                connection.execute("""INSERT INTO metric.query_workload VALUES
                    (%s,1,123,10,true,10,20,1,2,NULL,0,'SELECT $1','legacy-hash','alice',%s)""",
                    (datetime(2026,11,12,10,minute,tzinfo=timezone.utc), json.dumps({
                        "queryid":123,"userid":10,"dbid":5,"rows":7,
                        "wal_bytes":18446744073709551615,
                        "stats_since":"2026-11-12T00:00:00Z",
                        "shared_blk_read_time": 1.25,
                    })))
            connection.execute((ROOT / "migrations/sql/20261112_01_statement-reset-marker.sql").read_text())
            connection.execute((ROOT / "migrations/sql/20261112_02_typed-statements.sql").read_text())
            rows = connection.execute("SELECT wal_bytes,rows,source_database_oid,stats_since,statement_text_id,shared_blk_read_time FROM metric.query_workload").fetchall()
            assert len(rows) == 2
            assert rows[0][0] == Decimal("18446744073709551615")
            assert rows[0][1:3] == (7,5)
            assert rows[0][3].tzinfo is not None and rows[0][4] == rows[1][4]
            assert rows[0][5] == 1.25
            assert connection.execute("SELECT count(*) FROM metric.statement_text").fetchone()[0] == 1
            columns = connection.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='metric' AND table_name='query_workload'").fetchall()
            assert not {"query","query_hash","statement_data","statement_stats_since"} & {r[0] for r in columns}
            connection.execute((ROOT / "migrations/sql/20261112_02_typed-statements.rollback.sql").read_text())
            restored = connection.execute("SELECT statement_data::jsonb->>'wal_bytes',query FROM metric.query_workload").fetchall()
            assert len(restored) == 2 and restored[0] == ("18446744073709551615", "SELECT $1")
            connection.execute((ROOT / "migrations/sql/20261112_02_typed-statements.sql").read_text())
            assert connection.execute("SELECT count(*) FROM metric.query_workload").fetchone()[0] == 2
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
