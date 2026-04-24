import os
import sys

from yoyo import read_migrations, get_backend


def run_migrations():
    print("Starting migrations...")

    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "postgres")
    db_host = os.getenv("DB_HOST", "db")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "postgres")
    
    db_url = f"postgresql+psycopg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    try:
        backend = get_backend(db_url)
        migrations_dir = os.path.join(os.path.dirname(__file__), 'sql')
        migrations = read_migrations(migrations_dir)
        
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
