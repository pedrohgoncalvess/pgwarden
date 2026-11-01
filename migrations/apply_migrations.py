import os
import sys
from pathlib import Path
from urllib.parse import quote

from yoyo import read_migrations, get_backend


def get_migration_target() -> tuple[str, Path]:
    """Select independent SQLite migrations only for an explicit local setup."""
    directory = Path(__file__).resolve().parent
    backend = os.getenv("COLLECTOR_STORAGE_BACKEND", "postgresql").lower()
    if backend == "sqlite":
        filename = os.getenv("COLLECTOR_SQLITE_PATH")
        if not filename or filename == ":memory:":
            raise ValueError("COLLECTOR_SQLITE_PATH must name a persistent SQLite file")
        path = Path(filename).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{quote(path.as_posix(), safe='/')}", directory / "sqlite"
    if backend != "postgresql":
        raise ValueError("COLLECTOR_STORAGE_BACKEND must be postgresql or sqlite")

    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "postgres")
    db_host = os.getenv("DB_HOST", "db")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "postgres")

    db_url = (
        f"postgresql+psycopg://{quote(db_user, safe='')}:{quote(db_password, safe='')}"
        f"@{db_host}:{db_port}/{quote(db_name, safe='')}"
    )
    return db_url, directory / "sql"


def run_migrations() -> None:
    """Apply the selected backend's pending migrations using Yoyo."""
    print("Starting migrations...")
    try:
        db_url, migrations_dir = get_migration_target()
        backend = get_backend(db_url)
        migrations = read_migrations(str(migrations_dir))

        if not migrations:
            print("No migrations found.")
            return

        with backend.lock():
            pending = backend.to_apply(migrations)
            if pending:
                print(f"Applying {len(pending)} pending migrations...")
                backend.apply_migrations(pending)
                print("Migrations applied successfully.")
            else:
                print("No pending migrations to apply.")

    except Exception as e:
        print(f"Error applying migrations: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_migrations()
