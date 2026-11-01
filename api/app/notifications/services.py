from fastapi import HTTPException
from sqlalchemy import func, select, or_, and_
from app.access.policy import access_context
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.notifications.models import NotificationLevel, NotificationListResponse
from database.models.notifier.notification import Notification


def _level_expression() -> ColumnElement[str]:
    return func.coalesce(Notification.params["severity"].astext, "info")


async def list_notifications(
    db: AsyncSession,
    hidden: bool,
    level: NotificationLevel | None,
    limit: int,
    offset: int,
) -> NotificationListResponse:
    """Return notifications matching the requested visibility and level."""
    level_expression = _level_expression()
    access = access_context()
    scope = True
    if not access.admin:
        db_ids = list(access.databases) + [str(v) for v in access.databases.values()]
        server_ids = list(access.servers) + [str(v) for v in access.servers.values()]
        scope = or_(
            Notification.params['database_id'].astext.in_(db_ids),
            and_(Notification.params['database_id'].astext.is_(None),
                 or_(Notification.params['server_id'].astext.in_(server_ids),
                     and_(Notification.params['scope'].astext == 'server',
                          Notification.params['entity_id'].astext.in_(server_ids)))),
        )
    filters = [scope, Notification.hidden.is_(hidden)]
    if level:
        filters.append(level_expression == level)

    query = (
        select(Notification)
        .where(*filters)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list((await db.execute(query)).scalars().all())

    total = await db.scalar(select(func.count()).select_from(Notification).where(*filters))
    visible_count = await db.scalar(
        select(func.count()).select_from(Notification).where(scope, Notification.hidden.is_(False))
    )
    hidden_count = await db.scalar(
        select(func.count()).select_from(Notification).where(scope, Notification.hidden.is_(True))
    )

    level_query = (
        select(level_expression, func.count(Notification.id))
        .where(scope, Notification.hidden.is_(hidden))
        .group_by(level_expression)
    )
    level_rows = (await db.execute(level_query)).all()
    level_counts = {"critical": 0, "warning": 0, "info": 0}
    for notification_level, count in level_rows:
        normalized_level = (
            notification_level if notification_level in level_counts else "info"
        )
        level_counts[normalized_level] += count

    return NotificationListResponse(
        items=items,
        total=total or 0,
        visible_count=visible_count or 0,
        hidden_count=hidden_count or 0,
        level_counts=level_counts,
    )


async def set_notification_hidden(
    db: AsyncSession,
    notification_id: int,
    hidden: bool,
) -> Notification:
    """Hide or restore one notification."""
    notification = await db.get(Notification, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.hidden = hidden
    await db.commit()
    await db.refresh(notification)
    return notification
