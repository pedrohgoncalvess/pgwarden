"""Atomic event delivery, replay detection, and metric materialization."""

import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.auth import get_replacement_key
from app.ingestion.catalog import validate_row
from app.ingestion.entities import save_entity, save_observation
from app.ingestion.models import EventBatch
from app.projects.tables import event, project


async def receive_events(
    session: AsyncSession, settings: dict, key: dict, batch: EventBatch
) -> dict:
    """Acknowledge only after the entire batch and destination rows commit."""
    accepted = duplicates = 0
    for item in batch.events:
        data = validate_row(item.table, item.data)
        payload = item.model_dump(mode="json")
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        identity = {
            "project_id": settings["id"],
            "source_id": batch.source_id,
            "event_id": item.event_id,
        }
        inserted = (
            await session.execute(
                insert(event)
                .values(
                    **identity,
                    table_name=item.table,
                    fingerprint=fingerprint,
                    payload=payload,
                )
                .on_conflict_do_nothing()
                .returning(event.c.event_id)
            )
        ).scalar_one_or_none()
        if inserted is None:
            previous = (
                await session.execute(select(event.c.fingerprint).filter_by(**identity))
            ).scalar_one()
            if previous != fingerprint:
                raise HTTPException(
                    409, "An event_id was reused with different content"
                )
            duplicates += 1
            continue
        if item.table.startswith("metric_") or item.table == "metadata_index_column":
            await save_observation(session, settings, batch.source_id, item, data)
        else:
            await save_entity(session, settings, batch.source_id, item, data)
        accepted += 1
    replacement = await get_replacement_key(session, settings, key)
    await session.execute(
        update(project)
        .where(project.c.id == settings["id"])
        .values(last_event_at=datetime.now(timezone.utc))
    )
    await session.commit()
    return {
        "project_id": settings["id"],
        "accepted": accepted,
        "duplicates": duplicates,
        "acknowledged_event_ids": [item.event_id for item in batch.events],
        "replacement_key": replacement,
    }
