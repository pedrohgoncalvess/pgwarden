"""Administrator-managed users and roles; no public registration."""
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.models import RoleInput
from app.projects.router import require_admin
from database.connection import DatabaseConnection
from database.models.collector.server import Server
from database.models.metadata.database import Database

router = APIRouter(prefix='', tags=['access'], dependencies=[Depends(require_admin)])


async def validate_grants(conn: AsyncSession, role: RoleInput) -> None:
    """Reject grants whose parent project or server is missing."""
    projects = set((await conn.execute(text('SELECT id FROM ingestion.project'))).scalars())
    if not set(role.project_ids) <= projects:
        raise HTTPException(422, 'Unknown project')
    servers = (await conn.execute(select(Server).where(
        Server.public_id.in_(role.server_ids), Server.deleted_at.is_(None)
    ))).scalars().all()
    if len({s.public_id for s in servers}) != len(set(role.server_ids)):
        raise HTTPException(422, 'Unknown server')
    if any(
        server.ingestion_project_id is not None
        and server.ingestion_project_id not in role.project_ids
        for server in servers
    ):
        raise HTTPException(422, 'Select the parent project of every server')
    databases = (await conn.execute(select(Database).where(
        Database.public_id.in_(role.database_ids), Database.deleted_at.is_(None)
    ))).scalars().all()
    if len({d.public_id for d in databases}) != len(set(role.database_ids)):
        raise HTTPException(422, 'Unknown database')
    if any(d.server_id not in {s.id for s in servers} for d in databases):
        raise HTTPException(422, 'Select the parent server of every database')


@router.get('/roles')
async def list_roles() -> list[dict[str, Any]]:
    """List role definitions for administrators."""
    async with DatabaseConnection() as conn:
        result = await conn.execute(text('SELECT * FROM base.role ORDER BY name'))
        return [dict(row) for row in result.mappings()]


@router.post('/roles', status_code=201)
async def create_role(role: RoleInput) -> dict[str, Any]:
    """Create a role with explicit feature and resource grants."""
    return await save_role(None, role)


@router.put('/roles/{role_id}')
async def update_role(role_id: int, role: RoleInput) -> dict[str, Any]:
    """Replace a role and apply changes to subsequent requests."""
    return await save_role(role_id, role)


async def save_role(role_id: int | None, role: RoleInput) -> dict[str, Any]:
    """Validate and persist a complete role definition."""
    async with DatabaseConnection() as conn:
        await validate_grants(conn, role)
        params = role.model_dump() | {
            'permissions': json.dumps(role.permissions), 'id': role_id
        }
        if role_id:
            sql = '''UPDATE base.role SET name = :name,
                permissions = CAST(:permissions AS jsonb),
                project_ids = :project_ids, server_ids = :server_ids,
                database_ids = :database_ids WHERE id = :id RETURNING *'''
        else:
            sql = '''INSERT INTO base.role
                (name, permissions, project_ids, server_ids, database_ids)
                VALUES (:name, CAST(:permissions AS jsonb), :project_ids,
                        :server_ids, :database_ids) RETURNING *'''
        try:
            row = (await conn.execute(text(sql), params)).mappings().one_or_none()
            if row is None:
                raise HTTPException(404, 'Role not found')
            await conn.commit()
            return dict(row)
        except IntegrityError:
            await conn.rollback()
            raise HTTPException(409, 'Role name already exists')


@router.delete('/roles/{role_id}', status_code=204)
async def delete_role(role_id: int) -> Response:
    """Delete a role only when no account references it."""
    async with DatabaseConnection() as conn:
        try:
            result = await conn.execute(
                text('DELETE FROM base.role WHERE id = :id RETURNING id'),
                {'id': role_id},
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise HTTPException(404, 'Role not found')
            await conn.commit()
        except IntegrityError:
            await conn.rollback()
            raise HTTPException(409, 'This role is assigned to a user')
    return Response(status_code=204)
