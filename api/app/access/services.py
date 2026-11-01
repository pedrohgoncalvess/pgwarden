"""Request authorization. Resource grants always intersect their parent grants."""
from typing import AsyncIterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.policy import Access, current_access, require_permission
from app.access.targets import check_indirect_target, require_resource
from app.auth.services import get_current_user
from database.connection import DatabaseConnection
from database.models.base.user import User
from database.models.collector.server import Server
from database.models.metadata.database import Database


async def load_access(user: User, conn: AsyncSession) -> Access:
    """Intersect explicit grants with each resource's current ancestors."""
    if user.is_admin:
        return Access(admin=True, user_id=user.id)
    role_id = getattr(user, 'role_id', None)
    if role_id is None:
        return Access(user_id=user.id)
    result = await conn.execute(
        text('SELECT * FROM base.role WHERE id = :id'), {'id': role_id}
    )
    role = result.mappings().one_or_none()
    if not role:
        return Access(user_id=user.id)
    access = Access(
        user_id=user.id,
        permissions=set(role['permissions']),
        projects={str(value) for value in role['project_ids']},
    )
    servers = (await conn.execute(select(Server).where(
        Server.public_id.in_(role['server_ids']), Server.deleted_at.is_(None)
    ))).scalars().all()
    access.servers = {
        str(s.public_id): s.id for s in servers
        if s.ingestion_project_id is None or str(s.ingestion_project_id) in access.projects
    }
    databases = (await conn.execute(select(Database).where(
        Database.public_id.in_(role['database_ids']),
        Database.server_id.in_(list(access.servers.values())), Database.deleted_at.is_(None)
    ))).scalars().all()
    access.databases = {str(d.public_id): d.id for d in databases}
    return access


def required_permission(path: str, method: str) -> str | None:
    """Map read and write endpoints to independent feature capabilities."""
    write = method not in ('GET', 'HEAD', 'OPTIONS')
    mode = 'configure' if write else 'read'
    if path.startswith(('/v1/notifier', '/v1/notifications')):
        return f'alerts.{mode}'
    if (
        '/docs' in path
        or path.startswith(('/v1/tags', '/v1/search'))
        or '/schemas/history' in path
    ):
        return f'documentation.{mode}'
    if '/configs' in path or '/runs' in path or path.startswith('/v1/services'):
        return f'schedulers.{mode}'
    return None


async def authorize_request(
    request: Request, user: User = Depends(get_current_user)
) -> AsyncIterator[Access]:
    """Authorize the request before endpoint code reads or changes data."""
    async with DatabaseConnection() as conn:
        access = await load_access(user, conn)
        request.state.access = access
        path = request.url.path
        if not access.admin:
            permission = required_permission(path, request.method)
            if permission:
                require_permission(access, permission)
            elif request.method not in ('GET', 'HEAD', 'OPTIONS'):
                raise HTTPException(403, 'Administrator access required')
            if path.startswith('/v1/access'):
                raise HTTPException(403, 'Administrator access required')
            values = dict(request.query_params) | request.path_params
            if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                try:
                    body = await request.json()
                except ValueError:
                    body = {}
                if isinstance(body, dict):
                    values |= body
            for kind in ('project', 'server', 'database', 'table', 'column', 'index', 'tag'):
                # A body or query must not shadow an inaccessible URL target.
                for source in (request.path_params, request.query_params, values):
                    await require_resource(
                        conn, access, kind, source.get(f'{kind}_id')
                    )
            if values.get('target_id'):
                await require_resource(conn, access, values.get('target_type'), values['target_id'])
            if values.get('entity_public_id'):
                await require_resource(conn, access, values.get('scope'), values['entity_public_id'])
            await check_indirect_target(conn, access, request)
    token = current_access.set(access)
    try:
        yield access
    finally:
        current_access.reset(token)
