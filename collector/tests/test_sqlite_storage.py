"""Exercise standalone storage without requiring a central PostgreSQL server."""

import asyncio
import importlib
import re
import sqlite3
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from psycopg.rows import dict_row

from database.connection import DatabaseConnection
from database.load import load_storage_query
from database.sqlite_connection import SQLiteConnection
from database.storage import get_storage_backend, get_storage_connection


ROOT = Path(__file__).resolve().parents[2]


def reload_collector_queries():
    """Refresh import-time SQL when a test switches the process's backend."""
    for name, module in list(sys.modules.items()):
        if name.startswith("collector.collectors.") and hasattr(module, "load_storage_query"):
            importlib.reload(module)


@pytest.fixture
def storage(tmp_path, monkeypatch):
    path = tmp_path / "collector with spaces.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for migration in sorted((ROOT / "migrations/sqlite").glob("*.sql")):
            if not migration.name.endswith(".rollback.sql"):
                connection.executescript(migration.read_text())
    try:
        with monkeypatch.context() as environment:
            environment.setenv("COLLECTOR_STORAGE_BACKEND", "sqlite")
            environment.setenv("COLLECTOR_SQLITE_PATH", str(path))
            environment.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
            reload_collector_queries()
            yield get_storage_connection()
    finally:
        reload_collector_queries()


def test_postgresql_remains_default(monkeypatch):
    monkeypatch.delenv("COLLECTOR_STORAGE_BACKEND", raising=False)
    monkeypatch.setenv("DB_PASSWORD", "test-password")
    assert get_storage_backend() == "postgresql"
    assert isinstance(get_storage_connection(), DatabaseConnection)
    assert '"metadata"."table"' in load_storage_query("metadata", "table", "SELECT")


def test_invalid_storage_configuration(monkeypatch):
    monkeypatch.setenv("COLLECTOR_STORAGE_BACKEND", "unsupported")
    with pytest.raises(ValueError, match="postgresql or sqlite"):
        get_storage_connection()
    monkeypatch.setenv("COLLECTOR_STORAGE_BACKEND", "sqlite")
    for path in ("", ":memory:"):
        monkeypatch.setenv("COLLECTOR_SQLITE_PATH", path)
        with pytest.raises(ValueError, match="persistent SQLite file"):
            get_storage_connection()


@pytest.mark.asyncio
async def test_workload_snapshot_persists_and_deduplicates(storage):
    _, database_id = await register_target(storage)
    now = datetime.now(timezone.utc)
    values = dict(collected_at=now, database_id=database_id, query_id=-123, user_id=10,
                  is_toplevel=True, calls=200, total_exec_time=1234.5, shared_blks_read=5,
                  shared_blks_hit=30, stats_reset=now, dealloc=2,
                  query='SELECT $1', query_hash='abc', user_name='alice',
                  statement_data='{"wal_bytes": 100, "rows": 200}')
    query = load_storage_query('metric', 'query_workload', 'INSERT')
    async with storage as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.executemany(query, [values, values])
            await cursor.execute('SELECT * FROM metric_query_workload')
            rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]['is_toplevel'] is True
    assert rows[0]['stats_reset'] == now
    assert rows[0]['total_exec_time'] == 1234.5
    assert rows[0]['query_id'] == -123
    assert rows[0]['query'] == 'SELECT $1'
    assert rows[0]['statement_data'] == '{"wal_bytes": 100, "rows": 200}'


def test_all_sqlite_queries_match_schema(storage):
    source = ROOT / "collector/database/queries/storage"
    target = ROOT / "collector/database/queries/sqlite"
    with sqlite3.connect(storage.path) as connection:
        for path in source.rglob("*.toml"):
            relative = path.relative_to(source)
            postgres = tomllib.loads(path.read_text())
            sqlite = tomllib.loads((target / relative).read_text())
            assert postgres.keys() == sqlite.keys()
            for kind, queries in postgres.items():
                assert queries.keys() == sqlite[kind].keys()
                for name in queries:
                    query = sqlite[kind][name]
                    if relative.as_posix() == "metric/column.toml" and kind == "SELECT":
                        assert query == queries[name]
                        continue
                    values = dict.fromkeys(re.findall(r"%\((\w+)\)s", query))
                    query = re.sub(r"%\((\w+)\)s", r":\1", query)
                    connection.execute("EXPLAIN " + query, values)


async def register_target(storage):
    from config.upsert import _upsert_database, _upsert_server

    async with storage as connection:
        server_id = await _upsert_server(
            connection,
            {
                "name": "test",
                "host": "127.0.0.1",
                "port": 5432,
                "username": "monitor",
                "password": "secret",
                "ignore_tables": ["audit"],
            },
        )
        await _upsert_database(connection, server_id, "app")
    async with storage as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                load_storage_query("metadata", "database", "SELECT", "by_server_id"),
                {"server_id": server_id},
            )
            database_id = (await cursor.fetchone())["id"]
    return server_id, database_id


@pytest.mark.asyncio
async def test_bootstrap_registry_and_scheduling(storage):
    from database.registry import DatabaseRegistry
    from database.heartbeat import touch_heartbeat

    server_id, database_id = await register_target(storage)
    async with storage as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                load_storage_query("metadata", "database", "UPDATE", "set_oid"),
                {"id": database_id, "database_id": 123},
            )
            await cursor.execute(
                load_storage_query(
                    "collector", "config_database", "SELECT", "by_database_id"
                ),
                {"database_id": database_id},
            )
            configs = await cursor.fetchall()
            assert len(configs) == 11
            workload = next(c for c in configs if c['name'] == 'query_workload_collector')
            assert workload['interval'] == 60
            assert workload['is_paused']
            config = next(c for c in configs if c["name"] == "native_query_collector")
            assert config["interval"] == 0.5
            before = datetime.now(timezone.utc)
            await cursor.execute(
                load_storage_query("collector", "config_database", "UPDATE", "running"),
                {"id": config["id"]},
            )
            await cursor.execute(
                load_storage_query("collector", "config_database", "SELECT", "by_id"),
                {"id": config["id"]},
            )
            assert (
                0.4
                < ((await cursor.fetchone())["next_run_at"] - before).total_seconds()
                < 2
            )
        await touch_heartbeat(connection)
    registry = DatabaseRegistry(storage)
    await registry.sync()
    assert registry.server_ids() == [server_id]
    assert registry.all()[0].ignore_tables == ["audit"]
    assert "host=127.0.0.1" in registry.all()[0].conninfo
    assert isinstance(
        DatabaseConnection(conninfo=registry.all()[0].conninfo), DatabaseConnection
    )


@pytest.mark.asyncio
async def test_schema_sync_history_and_metrics(storage):
    from collector.collectors.schema.table import TableCollector
    from collector.collectors.schema.column import ColumnCollector
    from collector.collectors.schema.index import IndexCollector
    from database.registry import MonitoredDatabase

    server_id, database_id = await register_target(storage)
    db = MonitoredDatabase(database_id, server_id, "app", "unused")
    tables = TableCollector(None, storage, db)
    table = {
        "table_oid": 100,
        "schema_name": "public",
        "name": "users",
        "description": None,
    }
    await tables._sync([table], [])
    stored = await tables._fetch_stored()
    table_id = stored[0]["id"]
    await tables._sync([{**table, "name": "people"}], stored)

    columns = ColumnCollector(None, storage, db)
    column = {
        "table_oid": 100,
        "name": "id",
        "description": None,
        "data_type": "integer",
        "is_nullable": False,
        "is_unique": True,
        "ordinal_position": 1,
        "default_value": None,
        "foreign_table_oid": None,
    }
    await columns._sync([column], [])
    stored = await columns._fetch_stored()
    await columns._sync([{**column, "data_type": "bigint"}], stored)

    indexes = IndexCollector(None, storage, db)
    index = {
        "table_oid": 100,
        "index_oid": 200,
        "index_name": "users_pk",
        "index_type": "btree",
        "definition": "CREATE UNIQUE INDEX users_pk ON users(id)",
        "is_unique": True,
        "is_primary": True,
        "columns_info": [{"column_attnum": 1, "ordinal": 1}],
    }
    await indexes._sync([index], [])
    stored = await indexes._fetch_stored()
    assert stored[0]["columns_info"] == index["columns_info"]
    await indexes._sync([{**index, "index_name": "people_pk"}], stored)
    await columns._sync([], await columns._fetch_stored())
    await indexes._sync([], await indexes._fetch_stored())
    await tables._sync([], await tables._fetch_stored())

    async with storage as connection:
        async with connection.cursor() as cursor:
            for kind in ("table", "column", "index"):
                await cursor.execute(f"SELECT count(*) FROM metadata_{kind}_history")
                assert (await cursor.fetchone())[0] == 2
            query = load_storage_query("metric", "table", "INSERT")
            values = dict.fromkeys(re.findall(r"%\((\w+)\)s", query))
            values.update(collected_at=datetime.now(timezone.utc), table_id=table_id)
            await cursor.executemany(query, [values, values])
            await cursor.execute("SELECT count(*) FROM metric_table")
            assert (await cursor.fetchone())[0] == 1


@pytest.mark.asyncio
async def test_persistence_rollback_and_concurrent_writes(storage):
    server_id, _ = await register_target(storage)
    query = load_storage_query("metric", "cpu", "INSERT")

    async def write(sample):
        async with storage as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    query,
                    {
                        "collected_at": sample,
                        "server_id": server_id,
                        "cpu_percent": 10.5,
                        "cpu_count": 4,
                    },
                )

    await asyncio.gather(
        *(write(datetime(2026, 1, 1, 0, 0, n, tzinfo=timezone.utc)) for n in range(10))
    )
    with pytest.raises(RuntimeError):
        async with storage as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("DELETE FROM metric_cpu")
            raise RuntimeError("simulated crash")
    reopened = SQLiteConnection(storage.path)
    async with reopened as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT count(*) FROM metric_cpu")
            assert (await cursor.fetchone())[0] == 10
            with pytest.raises(sqlite3.IntegrityError):
                await cursor.execute(
                    query,
                    {
                        "collected_at": datetime.now(timezone.utc),
                        "server_id": 999,
                        "cpu_percent": 1,
                        "cpu_count": 1,
                    },
                )


@pytest.mark.asyncio
async def test_requires_existing_migrated_database(tmp_path):
    storage = SQLiteConnection(tmp_path / "missing.sqlite3")
    with pytest.raises(sqlite3.OperationalError):
        async with storage:
            pass
    assert not storage.path.exists()


@pytest.mark.asyncio
async def test_force_run_command_and_execution_status(storage, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from scheduler import loops

    _, database_id = await register_target(storage)
    async with storage as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                "SELECT id FROM collector_config_database WHERE database_id=%s LIMIT 1",
                (database_id,),
            )
            config_id = (await cursor.fetchone())["id"]
            await cursor.execute(
                "UPDATE collector_config_database SET is_paused=1 WHERE id=%s",
                (config_id,),
            )
            await cursor.execute(
                "INSERT INTO collector_command (collector, command, payload) VALUES (%s, %s, %s)",
                ("test:db", "force_run", {"requested": True}),
            )

    async def stop_loop(delay):
        raise asyncio.CancelledError

    monkeypatch.setattr(loops.asyncio, "sleep", stop_loop)
    collector = SimpleNamespace(collect=AsyncMock())
    with pytest.raises(asyncio.CancelledError):
        await loops.run_database_collector_loop(
            storage, collector, config_id, "test:db", database_id
        )
    collector.collect.assert_awaited_once()
    async with storage as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT status, command_id FROM collector_run")
            run = await cursor.fetchone()
            assert run["status"] == "success"
            assert run["command_id"] is not None
            await cursor.execute("SELECT executed_at, payload FROM collector_command")
            command = await cursor.fetchone()
            assert command["executed_at"].tzinfo is not None
            assert command["payload"] == {"requested": True}


@pytest.mark.asyncio
async def test_bootstrap_local_settings_and_restart(storage, monkeypatch):
    from config import main as configuration

    monkeypatch.setattr(
        configuration,
        "_load_config",
        lambda: {
            "servers": [
                {
                    "name": "local",
                    "host": "localhost",
                    "port": 5432,
                    "username": "monitor",
                    "password": "secret",
                    "databases": ["app"],
                    "server_metrics_enabled": False,
                }
            ],
            "collector": {
                "native_query_collector": {"interval": 2.5, "enabled": False},
                "query_workload_collector": {"interval": 3600, "enabled": True},
            },
        },
    )
    await configuration.bootstrap(storage)
    await configuration.bootstrap(storage)
    async with storage as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT count(*) AS total FROM metadata_database")
            assert (await cursor.fetchone())["total"] == 1
            await cursor.execute(
                "SELECT count(*) AS total FROM collector_config_server"
            )
            assert (await cursor.fetchone())["total"] == 0
            await cursor.execute(
                "SELECT interval, is_paused FROM collector_config_database WHERE name='native_query_collector'"
            )
            config = await cursor.fetchone()
            assert config == {"interval": 2.5, "is_paused": 1}
            await cursor.execute(
                "SELECT interval, is_paused FROM collector_config_database WHERE name='query_workload_collector'"
            )
            assert await cursor.fetchone() == {"interval": 3600, "is_paused": 0}


@pytest.mark.asyncio
async def test_missing_statements_auto_pauses_after_three_failures_and_survives_restart(storage, monkeypatch):
    from unittest.mock import AsyncMock
    from collector.collectors.metric import query_workload as workload
    from config import main as configuration

    _, database_id = await register_target(storage)
    async with storage as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE collector_config_database SET is_paused=0 WHERE name='query_workload_collector'")
    monkeypatch.setattr(workload, 'collect_query_workload', AsyncMock(side_effect=workload.StatementSourceUnavailable('missing extension')))
    warning_log = AsyncMock()
    monkeypatch.setattr(workload.logger, 'warn', warning_log)
    for attempt in range(1, 4):
        # A fresh instance models process restart; count is stored, not in RAM.
        collector = workload.QueryWorkloadMetricCollector(None, storage, database_id)
        with pytest.raises(workload.StatementSourceUnavailable):
            await collector.collect()
        async with storage as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT consecutive_errors, is_paused, warning FROM collector_config_database WHERE name='query_workload_collector'")
                state = await cur.fetchone()
        assert state['consecutive_errors'] == attempt
        assert bool(state['is_paused']) == (attempt == 3)
        assert bool(state['warning']) == (attempt == 3)
    warning_log.assert_awaited_once()
    monkeypatch.setattr(configuration, '_load_config', lambda: {'collector': {'query_workload_collector': {'interval': 60, 'enabled': True}}})
    await configuration._apply_collector_settings(storage)
    async with storage as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT is_paused, warning FROM collector_config_database WHERE name='query_workload_collector'")
            state = await cur.fetchone()
    assert state['is_paused'] and state['warning']


@pytest.mark.asyncio
async def test_success_and_other_errors_interrupt_missing_source_streak(storage, monkeypatch):
    from unittest.mock import AsyncMock
    from collector.collectors.metric import query_workload as workload

    _, database_id = await register_target(storage)
    collector = workload.QueryWorkloadMetricCollector(None, storage, database_id)
    collect = AsyncMock(side_effect=[
        workload.StatementSourceUnavailable('missing view'), 0,
        workload.StatementSourceUnavailable('missing view'), RuntimeError('permission denied'),
        workload.StatementSourceUnavailable('missing view'),
    ])
    monkeypatch.setattr(workload, 'collect_query_workload', collect)
    for error, count in [(workload.StatementSourceUnavailable, 1), (None, 0),
                         (workload.StatementSourceUnavailable, 1), (RuntimeError, 0),
                         (workload.StatementSourceUnavailable, 1)]:
        if error:
            with pytest.raises(error):
                await collector.collect()
        else:
            await collector.collect()
        async with storage as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT consecutive_errors, warning FROM collector_config_database WHERE name='query_workload_collector'")
                state = await cur.fetchone()
        assert state['consecutive_errors'] == count and state['warning'] is None
