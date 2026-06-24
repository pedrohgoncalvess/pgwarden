import asyncio
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, desc

from database.connection import DatabaseConnection
from database.models.metadata.database import Database
from database.models.metric.database_stat import DatabaseStat


def serialize_row(row) -> dict:
    data = {}
    for key, value in row.__dict__.items():
        if key.startswith("_"):
            continue
        if isinstance(value, datetime):
            data[key] = value.isoformat()
        else:
            data[key] = value
    return data


async def _fetch_latest_two(conn, database_id: int, last_ts):
    result = await conn.execute(
        select(DatabaseStat)
        .where(DatabaseStat.database_id == database_id)
        .order_by(desc(DatabaseStat.collected_at))
        .limit(2)
    )
    rows = result.scalars().all()

    if len(rows) < 2:
        return None, last_ts

    latest = rows[0]
    previous = rows[1]

    if last_ts and latest.collected_at <= last_ts:
        return None, last_ts

    new_ts = latest.collected_at

    delta_xact = (latest.xact_commit or 0) + (latest.xact_rollback or 0) - (previous.xact_commit or 0) - (previous.xact_rollback or 0)
    delta_t = (latest.collected_at - previous.collected_at).total_seconds()

    tps = delta_xact / delta_t if delta_t and delta_t > 0 else 0.0

    payload = {
        "collected_at": latest.collected_at.isoformat(),
        "database_id": database_id,
        "tps": round(tps, 3),
        "xact_commit": latest.xact_commit,
        "xact_rollback": latest.xact_rollback,
        "delta_xact": delta_xact,
        "delta_seconds": delta_t,
    }

    return payload, new_ts


async def database_metrics_stream(database_id: UUID):
    last_ts = None

    while True:
        try:
            async with DatabaseConnection() as conn:
                db_result = await conn.execute(
                    select(Database.id).where(Database.public_id == database_id)
                )
                internal_database_id = db_result.scalar_one_or_none()
                if internal_database_id is None:
                    yield {"event": "error", "data": json.dumps({"error": "Database not found"})}
                    await asyncio.sleep(2)
                    continue

                data, last_ts = await _fetch_latest_two(conn, internal_database_id, last_ts)

            if data is not None:
                yield {"event": "tps", "data": json.dumps(data)}

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

        await asyncio.sleep(2)
