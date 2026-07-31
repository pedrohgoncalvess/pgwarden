"""Read-only Analytics and Notifier service entries for the Runs workspace."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


SERVICE_TIMEOUT_SECONDS = 90


def _status(updated_at: datetime | None, paused: bool) -> str:
    """Derive a service run status from its heartbeat and enablement."""
    if paused:
        return "paused"
    if not updated_at or datetime.now(timezone.utc) - updated_at > timedelta(seconds=SERVICE_TIMEOUT_SECONDS):
        return "unavailable"
    return "idle"


async def get_service_runs(
    conn: AsyncSession, database_id: int, server_id: int, database_name: str
) -> list[dict[str, Any]]:
    """Return current Analytics and Notifier service schedules for one database."""
    heartbeats = await conn.execute(text("SELECT service, updated_at FROM base.service_heartbeat"))
    updated_at = {row.service: row.updated_at for row in heartbeats.mappings()}
    analytics = await conn.execute(
        text(
            """
            SELECT config.id, config.run_interval, config.query_analytics_enabled,
                   (
                     SELECT MIN(run.run_at) FROM analytics.run AS run
                     WHERE run.database_id = config.database_id AND run.run_at >= NOW()
                   ) AS next_run_at
            FROM analytics.config AS config
            WHERE config.database_id = :database_id
            """
        ),
        {"database_id": database_id},
    )
    config = analytics.mappings().one_or_none()
    analytics_paused = not bool(config and config["query_analytics_enabled"])
    notifier = await conn.execute(
        text(
            """
            SELECT COALESCE(MIN(interval_seconds) FILTER (WHERE enabled), 0) AS interval,
                   COALESCE(BOOL_OR(enabled), FALSE) AS enabled
            FROM notifier.rule
            """
        )
    )
    notifier_rule = notifier.mappings().one()
    notifier_paused = not bool(notifier_rule["enabled"])
    return [
        {
            "id": -1_000_000 - (config["id"] if config else database_id),
            "server_id": server_id,
            "database_id": database_id,
            "database_name": database_name,
            "name": "Analytics service",
            "type": "service",
            "interval": float(config["run_interval"] if config else 0),
            "is_paused": analytics_paused,
            "next_run_at": config["next_run_at"] if config else None,
            "status": _status(updated_at.get("analytics"), analytics_paused),
        },
        {
            "id": -2_000_000,
            "server_id": server_id,
            "database_id": database_id,
            "database_name": database_name,
            "name": "Notifier service",
            "type": "service",
            "interval": float(notifier_rule["interval"] or 0),
            "is_paused": notifier_paused,
            "next_run_at": None,
            "status": _status(updated_at.get("notifier"), notifier_paused),
        },
    ]


async def get_service_history(conn: AsyncSession, database_id: int) -> list[dict[str, Any]]:
    """Return persisted Analytics executions and Notifier deliveries for a database."""
    analytics = await conn.execute(
        text(
            """
            SELECT id, status, started_at, finished_at, error
            FROM analytics.run
            WHERE database_id = :database_id AND status IN ('completed', 'error')
            ORDER BY finished_at DESC
            LIMIT 100
            """
        ),
        {"database_id": database_id},
    )
    analytics_items = [
        {
            "id": -3_000_000 - row["id"],
            "name": "Analytics service",
            "type": "service",
            "status": "error" if row["status"] == "error" else "success",
            "errors": [row["error"]] if row["error"] else [],
            "started_at": _isoformat(row["started_at"]),
            "finished_at": _isoformat(row["finished_at"]),
        }
        for row in analytics.mappings()
    ]
    notifications = await conn.execute(
        text(
            """
            SELECT id, created_at
            FROM notifier.notification
            ORDER BY created_at DESC
            LIMIT 100
            """
        )
    )
    notifier_items = [
        {
            "id": -4_000_000 - row["id"],
            "name": "Notifier delivery",
            "type": "service",
            "status": "success",
            "errors": [],
            "started_at": _isoformat(row["created_at"]),
            "finished_at": _isoformat(row["created_at"]),
        }
        for row in notifications.mappings()
    ]
    return analytics_items + notifier_items


def _isoformat(value: datetime | None) -> str | None:
    """Serialize history timestamps to match collector run history."""
    return value.isoformat() if value else None


async def control_service_run(
    conn: AsyncSession, database_id: int, service: str, action: str
) -> dict[str, Any]:
    """Schedule, stop, or report the current state of a background service."""
    database = await conn.execute(
        text("SELECT server_id, db_name FROM metadata.database WHERE id = :database_id"),
        {"database_id": database_id},
    )
    database_row = database.mappings().one()
    if service == "analytics":
        if action == "force_run":
            config = await conn.execute(
                text("SELECT id FROM analytics.config WHERE database_id = :database_id"),
                {"database_id": database_id},
            )
            if config.scalar_one_or_none() is None:
                raise ValueError("Analytics has not been configured for this database")
            await conn.execute(
                text("INSERT INTO analytics.run (database_id, run_at) VALUES (:database_id, NOW())"),
                {"database_id": database_id},
            )
        elif action == "stop":
            await conn.execute(
                text(
                    "UPDATE analytics.config SET query_analytics_enabled = FALSE "
                    "WHERE database_id = :database_id"
                ),
                {"database_id": database_id},
            )
        else:
            raise ValueError("Analytics supports force_run or stop")
    elif service == "notifier":
        if action == "force_run":
            await conn.execute(
                text("INSERT INTO base.service_command (service, action) VALUES ('notifier', 'force_run')")
            )
        elif action == "stop":
            await conn.execute(text("UPDATE notifier.rule SET enabled = FALSE"))
        else:
            raise ValueError("Notifier supports force_run or stop")
    else:
        raise ValueError("Unknown service")

    await conn.commit()
    services = await get_service_runs(
        conn, database_id, database_row["server_id"], database_row["db_name"]
    )
    return next(item for item in services if item["name"].lower().startswith(service))
