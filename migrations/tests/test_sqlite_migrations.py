"""Verify the independent collector SQLite migrations through Yoyo."""

import sqlite3
import pytest
from yoyo import get_backend, read_migrations

from apply_migrations import get_migration_target, run_migrations


def test_default_target_still_uses_postgresql(monkeypatch):
    monkeypatch.delenv("COLLECTOR_STORAGE_BACKEND", raising=False)
    url, directory = get_migration_target()
    assert url.startswith("postgresql+psycopg://")
    assert directory.name == "sql"


def test_sqlite_apply_repeat_and_rollback(tmp_path, monkeypatch):
    path = tmp_path / "nested folder" / "collector.sqlite3"
    monkeypatch.setenv("COLLECTOR_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("COLLECTOR_SQLITE_PATH", str(path))
    run_migrations()
    run_migrations()
    assert path.exists()
    url, directory = get_migration_target()
    backend = get_backend(url)
    migrations = read_migrations(str(directory))
    assert len(migrations) == 9
    assert not backend.to_apply(migrations)
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "collector_server",
            "collector_run",
            "metadata_table",
            "metric_native_query",
            "metric_query_workload",
        } <= tables
        assert not any(
            name.startswith(("notifier_", "analytics_", "doc_")) for name in tables
        )
    backend.connection.execute("PRAGMA foreign_keys=ON")
    with backend.lock():
        backend.rollback_migrations(backend.to_rollback(migrations))
    assert len(backend.to_apply(migrations)) == 9
    backend.connection.close()


@pytest.mark.parametrize(
    "backend, filename",
    [("other", "file.sqlite3"), ("sqlite", ""), ("sqlite", ":memory:")],
)
def test_invalid_target(backend, filename, monkeypatch):
    monkeypatch.setenv("COLLECTOR_STORAGE_BACKEND", backend)
    monkeypatch.setenv("COLLECTOR_SQLITE_PATH", filename)
    with pytest.raises(ValueError):
        get_migration_target()
