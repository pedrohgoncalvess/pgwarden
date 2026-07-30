import os
import glob

import pytest


def test_ensure_every_migration_has_rollback():
    migrations_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sql")
    all_files = glob.glob(os.path.join(migrations_path, "*.sql"))

    migration_files = {
        f for f in all_files if not f.endswith(".rollback.sql")
    }
    rollback_files = {
        f.removesuffix(".rollback.sql") + ".sql"
        for f in all_files
        if f.endswith(".rollback.sql")
    }

    missing_rollbacks = sorted(
        os.path.basename(path) for path in migration_files - rollback_files
    )
    orphan_rollbacks = sorted(
        os.path.basename(path).replace(".sql", ".rollback.sql")
        for path in rollback_files - migration_files
    )

    assert not missing_rollbacks, f"The following migrations are missing rollback files: {missing_rollbacks}"
    assert not orphan_rollbacks, f"The following rollback files have no migration: {orphan_rollbacks}"

def test_apply_and_rollback_all_migrations(setup_migration_db, backend, migrations):
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))

    unapplied = [migration.id for migration in migrations if not backend.is_applied(migration)]
    assert not unapplied, f"Migrations were not applied: {unapplied}"

    with backend.lock():
        backend.rollback_migrations(backend.to_rollback(migrations))

    still_applied = [migration.id for migration in migrations if backend.is_applied(migration)]
    assert not still_applied, f"Migrations were not rolled back: {still_applied}"
