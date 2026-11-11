"""Estimate logical row volume under inherited policies without claiming disk release."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.retention.models import RetentionWindow
from app.retention.ownership import get_owner, list_tables
from app.retention.scopes import resolve_policy, validate_scope


async def preview_scope(
    session: AsyncSession, scope: str, scope_id: UUID, name: str,
    window: RetentionWindow,
) -> dict[str, Any]:
    """Count affected rows, honoring more specific overrides in a proposed policy."""
    await validate_scope(session, scope, scope_id)
    names = await list_tables(session)
    if name != "*":
        from fastapi import HTTPException
        if name not in names:
            raise HTTPException(404, "Metric table not found")
        names = [name]
    servers = [dict(row) for row in (await session.execute(text("""
        SELECT id,public_id,name,ingestion_project_id FROM collector.server
        WHERE :scope='global' OR (:scope='server' AND public_id=:id)
           OR (:scope='project' AND ingestion_project_id=:id)
        ORDER BY id
    """), {"scope": scope, "id": scope_id})).mappings()]
    rows = []
    timing = (await session.execute(text("""
        SELECT now() AS measured_at, now()-CAST(CAST(:duration AS text) AS interval) AS cutoff,
            EXTRACT(EPOCH FROM (now()-(now()-CAST(CAST(:duration AS text) AS interval)))) AS seconds
    """), {"duration": f"{window.value} {window.unit}"})).mappings().one()
    for server in servers:
        for table in names:
            current = await resolve_policy(session, server, table)
            current_rank = {"server": 0, "project": 1, "global": 2}.get(
                current["scope"] if current else "global", 2)
            rank = {"server": 0, "project": 1, "global": 2}[scope]
            preserved = bool(current and (current_rank < rank or (
                current_rank == rank and name == "*" and current["table_name"] != "*") or (
                current_rank == rank and current["table_name"] == name and not current["enabled"])))
            if preserved:
                rows.append({"server_id": server["public_id"], "server_name": server["name"],
                             "name": table, "preserved": True, "current_policy": current})
                continue
            data = (await session.execute(text(f"""
                SELECT count(*) AS rows, count(*) FILTER (WHERE m.collected_at < :cutoff) AS expired_rows,
                    COALESCE(sum(pg_column_size(m)),0) AS logical_bytes,
                    COALESCE(sum(pg_column_size(m)) FILTER (WHERE m.collected_at < :cutoff),0) AS expired_bytes,
                    min(m.collected_at) AS first_sample,max(m.collected_at) AS last_sample
                FROM metric."{table}" m WHERE {get_owner(table)}=:server
            """), {"server": server["id"], "cutoff": timing["cutoff"]})).mappings().one()
            span = ((timing["measured_at"]-data["first_sample"]).total_seconds()
                    if data["first_sample"] else 0)
            projected = (round(int(data["logical_bytes"])/span*float(timing["seconds"]))
                         if span >= 60 and data["last_sample"] > data["first_sample"] else None)
            rows.append({"server_id": server["public_id"], "server_name": server["name"],
                         "name": table, "preserved": False, "current_policy": current,
                         **dict(data), "projected_bytes": projected})
    affected = [item for item in rows if not item["preserved"]]
    return {"scope": scope, "scope_id": scope_id, "name": name,
            "window": window.model_dump(), "measured_at": timing["measured_at"],
            "tables": rows, "affected_tables": len(affected),
            "expired_rows": sum(item["expired_rows"] for item in affected),
            "expired_bytes": sum(int(item["expired_bytes"]) for item in affected),
            "logical_bytes": sum(int(item["logical_bytes"]) for item in affected),
            "projected_bytes": sum(item["projected_bytes"] for item in affected)
            if affected and all(item["projected_bytes"] is not None for item in affected) else None}
