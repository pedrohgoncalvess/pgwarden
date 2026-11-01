import tomllib
from pathlib import Path

from utils import project_root
from database.storage import get_storage_backend


def load_monitored_query(query_type: str):
    base_path = Path(project_root) / "database"
    full_path = base_path / "queries" / "monitored" / f"{query_type.lower()}.sql"
    with full_path.open("r", encoding="utf-8") as f:
        return f.read()


def load_storage_query(schema: str, table: str, query_type: str, query_name: str = "default"):
    base_path = Path(project_root) / "database"
    directory = "sqlite" if get_storage_backend() == "sqlite" else "storage"
    full_path = base_path / "queries" / directory / schema.lower() / f"{table.lower()}.toml"
    with full_path.open("rb") as f:
        data = tomllib.load(f)

    return data[query_type.upper()][query_name]
