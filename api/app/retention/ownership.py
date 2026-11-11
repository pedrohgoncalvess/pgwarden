"""Allowlisted metric ownership and primary keys for scoped deletion."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


TABLE_NAMES = (
    "column", "cpu", "database_stat", "disk", "index", "io", "lock",
    "native_query", "query_workload", "ram", "session", "table",
)


def get_owner(name: str) -> str:
    """Return a correlated ownership expression for an allowlisted metric."""
    if name not in TABLE_NAMES:
        raise ValueError("Unsupported metric table")
    if name in ("cpu", "disk", "io", "ram"):
        return "m.server_id"
    if name in ("database_stat", "lock", "native_query", "query_workload", "session"):
        return "(SELECT d.server_id FROM metadata.database d WHERE d.id=m.database_id)"
    if name in ("table", "index"):
        return (f'(SELECT d.server_id FROM metadata."{name}" e '
                f'JOIN metadata.database d ON d.id=e.database_id WHERE e.id=m.{name}_id)')
    return ('(SELECT d.server_id FROM metadata."column" c '
            'JOIN metadata."table" t ON t.id=c.table_id '
            'JOIN metadata.database d ON d.id=t.database_id WHERE c.id=m.column_id)')


async def list_tables(session: AsyncSession) -> list[str]:
    """Include ordinary metric tables as well as hypertables."""
    return list((await session.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='metric' AND table_name = ANY(:names)
        ORDER BY table_name
    """), {"names": list(TABLE_NAMES)})).scalars())


async def get_keys(session: AsyncSession, name: str) -> list[str]:
    """Read primary keys without depending on physical row identifiers."""
    get_owner(name)
    keys = list((await session.execute(text("""
        SELECT a.attname FROM pg_index i
        JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)
        WHERE i.indrelid=CAST(:relation AS regclass) AND i.indisprimary
        ORDER BY a.attnum
    """), {"relation": f'metric."{name}"'})).scalars())
    if not keys:
        raise ValueError(f"metric.{name} has no primary key; refusing unbounded cleanup")
    return keys
