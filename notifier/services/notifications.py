import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from notifier.channels.base import Alert


def path_for(scope: str, entity_id: int | None, database_id: int | None) -> str | None:
    if scope == "server":
        return "/servers"
    if scope == "database" and entity_id is not None:
        return f"/overview/{entity_id}"
    if scope == "table" and database_id is not None:
        return f"/analytics/{database_id}/data"
    if scope == "index" and database_id is not None:
        return f"/analytics/{database_id}/index"
    return None


async def insert_notification(session: AsyncSession, alert: Alert) -> None:
    params = await build_params(session, alert)
    await session.execute(
        text("INSERT INTO notifier.notification (message, params) VALUES (:message, :params)"),
        {"message": alert.format_plain(), "params": json.dumps(params)},
    )


async def build_params(session: AsyncSession, alert: Alert) -> dict[str, Any]:
    database_id = await _resolve_database_id(session, alert)
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=alert.window_minutes)

    return {
        "path": path_for(alert.scope, alert.entity_id, database_id),
        "scope": alert.scope,
        "type": alert.rule,
        "rule": alert.rule_name,
        "entity": alert.entity,
        "entity_id": alert.entity_id,
        "database_id": database_id,
        "severity": alert.severity,
        "value": alert.value,
        "threshold": alert.threshold,
        "from": start.isoformat(),
        "to": now.isoformat(),
    }


async def _resolve_database_id(session: AsyncSession, alert: Alert) -> int | None:
    if alert.scope == "database":
        return alert.entity_id
    if alert.entity_id is None:
        return None
    if alert.scope == "table":
        result = await session.execute(
            text("SELECT database_id FROM metadata.table WHERE id = :id"),
            {"id": alert.entity_id},
        )
    elif alert.scope == "index":
        result = await session.execute(
            text("SELECT database_id FROM metadata.index WHERE id = :id"),
            {"id": alert.entity_id},
        )
    else:
        return None

    row = result.first()
    return row[0] if row else None
