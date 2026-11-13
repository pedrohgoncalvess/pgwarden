"""Expose structured statement statistics without storing serialized payloads."""

from datetime import datetime
from decimal import Decimal

from database.models.metric.statement_fields import EXTRA_FIELDS


def get_statistics(row: object) -> dict:
    """Build the existing response shape from typed columns and SQL text."""
    result = {name: getattr(row, name, None) for name in EXTRA_FIELDS}
    result.pop("source_database_oid")
    result.update(
        queryid=str(row.query_id), userid=row.user_id,
        dbid=getattr(row, "source_database_oid", None), toplevel=row.is_toplevel,
        query=row.query, calls=row.calls, total_exec_time=row.total_exec_time,
        shared_blks_read=row.shared_blks_read, shared_blks_hit=row.shared_blks_hit,
    )
    return {name: value.isoformat() if isinstance(value, datetime) else
            str(value) if isinstance(value, Decimal) else value
            for name, value in result.items()}
