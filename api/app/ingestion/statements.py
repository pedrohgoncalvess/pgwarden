"""Accept legacy queued events while persisting only typed statement data."""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.metric.query_workload import StatementText
from database.models.metric.statement_fields import EXTRA_FIELDS


def expand_legacy_statement(data: dict) -> dict:
    """Map legacy JSON fields without allowing them to overwrite event identity."""
    values = dict(data)
    raw = values.pop("statement_data", None)
    if raw is not None:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Statement statistics must be a JSON object")
        known = set(EXTRA_FIELDS) | {
            "queryid", "userid", "dbid", "toplevel", "query", "calls",
            "total_exec_time", "shared_blks_read", "shared_blks_hit",
        }
        if set(payload) - known:
            raise ValueError("Unsupported statement statistics fields")
        for name in EXTRA_FIELDS:
            source = "dbid" if name == "source_database_oid" else name
            if name not in values and payload.get(source) is not None:
                values[name] = payload[source]
    return values


async def resolve_statement_text(session: AsyncSession, data: dict) -> dict:
    """Resolve a database-scoped SQL fingerprint inside the ingestion transaction."""
    values = dict(data)
    query = values.pop("query", None)
    values.pop("query_hash", None)
    if query is None:
        values["statement_text_id"] = None
        return values
    fingerprint = hashlib.sha256(query.encode()).hexdigest()
    table = StatementText.__table__
    await session.execute(insert(table).values(
        database_id=values["database_id"], fingerprint=fingerprint, query=query,
        query_hash=hashlib.md5(query.encode(), usedforsecurity=False).hexdigest(),
    ).on_conflict_do_nothing(index_elements=[table.c.database_id, table.c.fingerprint]))
    row = (await session.execute(select(table.c.id, table.c.query).where(
        table.c.database_id == values["database_id"], table.c.fingerprint == fingerprint,
    ))).one()
    if row.query != query:
        raise ValueError("Statement text fingerprint collision")
    values["statement_text_id"] = row.id
    return values
