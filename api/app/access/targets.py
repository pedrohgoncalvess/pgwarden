"""Resolve resource identifiers before allowing access to scoped data."""
from uuid import UUID
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.access.policy import Access


async def require_resource(
    conn: AsyncSession, access: Access, kind: str | None, value: Any
) -> None:
    """Validate a public identifier against its effective parent grants."""
    if value is None or access.admin:
        return
    if kind in ('server', 'database', 'project'):
        allowed = {'server': access.servers, 'database': access.databases, 'project': access.projects}[kind]
        if str(value) not in allowed:
            raise HTTPException(404, 'Resource not found')
        return
    # Fixed identifiers only; never interpolate caller-supplied table names.
    names = {'table': 'metadata."table"', 'column': 'metadata."column"',
             'index': 'metadata."index"', 'tag': 'doc.tag'}
    if not isinstance(kind, str) or kind not in names:
        raise HTTPException(404, 'Resource not found')
    try:
        public_id = UUID(str(value))
    except ValueError:
        raise HTTPException(404, 'Resource not found')
    parent = 'server_id' if kind == 'tag' else 'database_id'
    query = (
        'SELECT t.database_id FROM metadata."column" c '
        'JOIN metadata."table" t ON t.id = c.table_id WHERE c.public_id = :id'
        if kind == 'column' else
        f'SELECT {parent} FROM {names[kind]} WHERE public_id = :id'
    )
    row = (await conn.execute(text(query), {'id': public_id})).scalar_one_or_none()
    allowed = access.servers if kind == 'tag' else access.databases
    if row is None or row not in allowed.values():
        raise HTTPException(404, 'Resource not found')


def _numeric_id(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(404, 'Resource not found')


async def check_indirect_target(
    conn: AsyncSession, access: Access, request: Request
) -> None:
    """Numeric IDs must not bypass the URL's resource scope."""
    params = request.path_params
    path = request.url.path
    if 'run_id' in params:
        table = 'config_server' if 'server_id' in params else 'config_database'
        parent = 'server_id' if table == 'config_server' else 'database_id'
        result = await conn.execute(
            text(f'SELECT {parent} FROM collector.{table} WHERE id = :id'),
            {'id': _numeric_id(params['run_id'])},
        )
        row = result.scalar_one_or_none()
        grants = access.servers if table == 'config_server' else access.databases
        if row is None or row != grants.get(str(params.get(parent))):
            raise HTTPException(404, 'Run not found')
    if path.startswith('/v1/services/') and 'config_id' in params:
        result = await conn.execute(
            text('SELECT database_id FROM analytics.config WHERE id = :id'),
            {'id': _numeric_id(params['config_id'])},
        )
        row = result.scalar_one_or_none()
        if row not in access.databases.values():
            raise HTTPException(404, 'Configuration not found')
    if 'threshold_id' in params:
        scope = params.get('scope')
        if scope not in ('server', 'database', 'table', 'index'):
            raise HTTPException(404, 'Threshold not found')
        from database.operations.notifier import threshold_repository
        threshold = await threshold_repository(scope, conn).find_by_id(
            _numeric_id(params['threshold_id'])
        )
        if threshold is None or not await threshold_visible(
            conn, access, scope, threshold
        ):
            raise HTTPException(404, 'Threshold not found')
    if 'notification_id' in params:
        from database.models.notifier.notification import Notification
        row = await conn.get(Notification, _numeric_id(params['notification_id']))
        if row is None or not notification_visible(access, row.params):
            raise HTTPException(404, 'Notification not found')


async def threshold_visible(
    conn: AsyncSession, access: Access, scope: str, row: Any
) -> bool:
    """Check the entity targeted by a threshold."""
    if access.admin:
        return True
    entity_id = getattr(row, f'{scope}_id')
    if entity_id is None:
        return True
    if scope in ('server', 'database'):
        grants = access.servers if scope == 'server' else access.databases
        return entity_id in grants.values()
    table = 'metadata."table"' if scope == 'table' else 'metadata."index"'
    result = await conn.execute(
        text(f'SELECT database_id FROM {table} WHERE id = :id'), {'id': entity_id}
    )
    database_id = result.scalar_one_or_none()
    return database_id in access.databases.values()


def notification_visible(access: Access, params: dict) -> bool:
    """Allow scoped notifications only when their resource is accessible."""
    if access.admin:
        return True
    # Only explicitly scoped notifications are safe to disclose to a restricted user.
    db_id = params.get('database_id')
    server_id = params.get('server_id')
    if db_id is not None:
        return str(db_id) in access.databases or str(db_id) in {
            str(value) for value in access.databases.values()
        }
    if server_id is None and params.get('scope') == 'server':
        server_id = params.get('entity_id')
    if server_id is not None:
        return str(server_id) in access.servers or str(server_id) in {
            str(value) for value in access.servers.values()
        }
    return False
