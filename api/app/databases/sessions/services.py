import asyncio
import json
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, desc

from database.connection import DatabaseConnection
from database.models.metadata.database import Database
from database.models.metric.session import SessionMetric


def serialize_row(row) -> dict:
    return jsonable_encoder({
        key: value for key, value in row.__dict__.items() if not key.startswith("_")
    })


async def session_stream(database_id: UUID):
    last_ts = None

    while True:
        event = None
        try:
            async with DatabaseConnection() as conn:
                db_result = await conn.execute(
                    select(Database.id).where(Database.public_id == database_id)
                )
                internal_database_id = db_result.scalar_one_or_none()
                if internal_database_id is None:
                    raise LookupError('Database not found')

                result = await conn.execute(
                    select(SessionMetric)
                    .where(SessionMetric.database_id == internal_database_id)
                    .order_by(desc(SessionMetric.collected_at))
                    .limit(1)
                )
                latest = result.scalar_one_or_none()

                if latest and (last_ts is None or latest.collected_at > last_ts):
                    last_ts = latest.collected_at
                    rows_result = await conn.execute(
                        select(SessionMetric)
                        .where(
                            SessionMetric.database_id == internal_database_id,
                            SessionMetric.collected_at == last_ts,
                        )
                    )
                    rows = rows_result.scalars().all()
                    payload = [serialize_row(r) for r in rows]
                    event = {"event": "sessions", "data": json.dumps(payload)}

            if event is not None:
                yield event

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

        await asyncio.sleep(2)
