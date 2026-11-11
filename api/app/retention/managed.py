"""Compatibility views for table defaults managed by the scoped worker."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.retention.ownership import list_tables


async def list_defaults(session: AsyncSession) -> list[dict[str, Any]]:
    """Show global table defaults without exposing them as native chunk policies."""
    result = []
    for name in await list_tables(session):
        row = (await session.execute(text("""
            SELECT duration::text AS retention_interval, enabled,
                EXTRACT(EPOCH FROM (now()-(now()-duration))) AS seconds
            FROM retention.policy WHERE scope='global' AND table_name IN (:name,'*')
            ORDER BY CASE WHEN table_name=:name THEN 0 ELSE 1 END LIMIT 1
        """), {"name": name})).mappings().one_or_none()
        result.append({"name": name, "managed": True,
                       "job_id": 0 if row else None,
                       "retention_interval": row["retention_interval"] if row else None,
                       "retention_seconds": row["seconds"] if row else None,
                       "scheduled": row["enabled"] if row else None,
                       "schedule_interval": "1 minute", "next_start": None,
                       "last_run_status": None})
    return result
