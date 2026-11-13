"""Convert structured extension rows into normalized local snapshots."""

import hashlib
from datetime import datetime

from database.statement_fields import EXTRA_FIELDS


def prepare_statement(row: dict, database_id: int, collected_at: datetime) -> dict:
    """Preserve exact numeric values and missing-version fields without JSON."""
    known = set(EXTRA_FIELDS) | {
        "queryid", "userid", "dbid", "toplevel", "query", "query_hash",
        "calls", "total_exec_time", "shared_blks_read", "shared_blks_hit",
        "stats_reset", "dealloc", "user_name",
    }
    if unknown := set(row) - known:
        raise ValueError(f"Unsupported statement statistics fields: {sorted(unknown)}")
    values = {name: row.get(name) for name in EXTRA_FIELDS}
    values.update({name: row[name] for name in (
        "calls", "total_exec_time", "shared_blks_read", "shared_blks_hit",
        "stats_reset", "dealloc", "user_name",
    )})
    query = row.get("query")
    values.update(
        collected_at=collected_at, database_id=database_id,
        query_id=row["queryid"], user_id=row["userid"], is_toplevel=row["toplevel"],
        source_database_oid=row.get("dbid"), query=query,
        fingerprint=hashlib.sha256(query.encode()).hexdigest() if query is not None else None,
        query_hash=hashlib.md5(query.encode(), usedforsecurity=False).hexdigest() if query is not None else None,
    )
    if values["wal_bytes"] is not None:
        values["wal_bytes"] = str(values["wal_bytes"])
    return values
