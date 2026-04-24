import os
import glob

import pytest


def test_ensure_every_migration_has_rollback():
    """
    Ensures that every .sql file in the migrations directory has a corresponding .rollback.sql file.
    Failure to provide a rollback will break this test.
    """
    migrations_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sql")
    all_files = glob.glob(os.path.join(migrations_path, "*.sql"))
    
    migration_files = [f for f in all_files if not f.endswith(".rollback.sql")]
    
    missing_rollbacks = []
    for migration in migration_files:
        rollback = migration.replace(".sql", ".rollback.sql")
        if not os.path.exists(rollback):
            missing_rollbacks.append(os.path.basename(migration))
            
    assert not missing_rollbacks, f"The following migrations are missing rollback files: {missing_rollbacks}"

def test_apply_and_rollback_all_migrations(setup_migration_db, backend, migrations):
    """
    Executes a full cycle of applying all migrations and then rolling them back.
    This ensures that both the schema creation and destruction SQL are syntactically correct.
    """
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))
        
    applied = backend.is_applied(migrations[0]) if migrations else True
    assert applied, "First migration should be applied"
    
    with backend.lock():
        backend.rollback_migrations(backend.to_rollback(migrations))
        
    if migrations:
        assert not backend.is_applied(migrations[0]), "First migration should be rolled back"
