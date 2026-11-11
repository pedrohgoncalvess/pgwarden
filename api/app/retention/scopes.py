"""Persist policy inheritance under the cleanup coordination lock."""

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.retention.models import RetentionWindow
from app.retention.ownership import list_tables


GLOBAL_ID = UUID(int=0)
LOCK_KEY = 1885824114


async def lock_policies(session: AsyncSession) -> None:
    """Serialize policy changes with each bounded cleanup transaction."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})


async def validate_scope(session: AsyncSession, scope: str, scope_id: UUID) -> None:
    """Reject nonexistent or mismatched policy targets."""
    if scope == "global" and scope_id == GLOBAL_ID:
        return
    if scope not in ("project", "server") or scope_id == GLOBAL_ID:
        raise HTTPException(422, "Invalid retention scope")
    query = ("SELECT 1 FROM ingestion.project WHERE id=:id" if scope == "project"
             else "SELECT 1 FROM collector.server WHERE public_id=:id AND deleted_at IS NULL")
    if not await session.scalar(text(query), {"id": scope_id}):
        raise HTTPException(404, "Retention scope not found")


async def resolve_policy(
    session: AsyncSession, server: dict[str, Any], name: str
) -> dict[str, Any] | None:
    """Resolve server, then project, then global, with table-specific priority."""
    result = await session.execute(text("""
        SELECT *, duration::text AS retention_interval FROM retention.policy
        WHERE table_name IN ('*', :name) AND (
            (scope='server' AND scope_id=:server) OR
            (scope='project' AND scope_id=:project) OR
            (scope='global'))
        ORDER BY CASE scope WHEN 'server' THEN 0 WHEN 'project' THEN 1 ELSE 2 END,
                 CASE WHEN table_name=:name THEN 0 ELSE 1 END
        LIMIT 1
    """), {"name": name, "server": server["public_id"],
           "project": server["ingestion_project_id"]})
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def save_policy(
    session: AsyncSession, scope: str, scope_id: UUID, name: str,
    window: RetentionWindow,
) -> None:
    """Upsert a scope or table override without committing the caller's transaction."""
    await lock_policies(session)
    await validate_scope(session, scope, scope_id)
    if name != "*" and name not in await list_tables(session):
        raise HTTPException(404, "Metric table not found")
    await session.execute(text("""
        INSERT INTO retention.policy(scope,scope_id,table_name,value,unit,duration)
        VALUES (:scope,:id,:name,:value,:unit,CAST(CAST(:duration AS text) AS interval))
        ON CONFLICT(scope,scope_id,table_name) DO UPDATE SET
            value=EXCLUDED.value, unit=EXCLUDED.unit, duration=EXCLUDED.duration,
            updated_at=now()
    """), {"scope": scope, "id": scope_id, "name": name,
           "value": window.value, "unit": window.unit,
           "duration": f"{window.value} {window.unit}"})


async def remove_policy(
    session: AsyncSession, scope: str, scope_id: UUID, name: str,
) -> None:
    """Remove an override so its parent policy becomes effective again."""
    if scope == "global":
        raise HTTPException(422, "Only project and server overrides can inherit")
    await lock_policies(session)
    await validate_scope(session, scope, scope_id)
    await session.execute(text("""
        DELETE FROM retention.policy WHERE scope=:scope AND scope_id=:id AND table_name=:name
    """), {"scope": scope, "id": scope_id, "name": name})


async def list_settings(session: AsyncSession) -> dict[str, Any]:
    """Return targets, overrides, and the effective policy for every server/table."""
    tables = await list_tables(session)
    servers = [dict(row) for row in (await session.execute(text("""
        SELECT id,public_id,name,ingestion_project_id,deleted_at FROM collector.server
        ORDER BY name,id
    """))).mappings()]
    policies = [dict(row) for row in (await session.execute(text("""
        SELECT *,duration::text AS retention_interval FROM retention.policy
        ORDER BY scope,scope_id,table_name
    """))).mappings()]
    effective = []
    indexed = {(item["scope"], item["scope_id"], item["table_name"]): item for item in policies}
    for server in servers:
        for name in tables:
            policy = next((indexed[key] for key in (
                (scope, identifier, table) for scope, identifier in (
                    ("server", server["public_id"]),
                    ("project", server["ingestion_project_id"]),
                    ("global", GLOBAL_ID),
                ) for table in (name, "*")
            ) if key in indexed), None)
            effective.append({"server_id": server["public_id"], "name": name,
                              "policy": policy})
    projects = [dict(row) for row in (await session.execute(text(
        "SELECT id,name FROM ingestion.project ORDER BY name"
    ))).mappings()]
    runs = [dict(row) for row in (await session.execute(text(
        "SELECT r.*,s.public_id FROM retention.run r JOIN collector.server s ON s.id=r.server_id"
    ))).mappings()]
    return {"tables": tables, "servers": servers, "projects": projects,
            "policies": policies, "effective": effective, "runs": runs}
