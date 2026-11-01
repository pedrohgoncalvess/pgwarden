"""Resolve source-local identities without accepting central database IDs."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.catalog import REFERENCES, TABLES
from app.ingestion.models import CollectionEvent
from app.projects.tables import entity
from utils import encrypt


def get_identity(project_id: UUID, source_id: UUID, name: str, local_id: int) -> list:
    """Build the complete namespace for one remote entity."""
    return [
        entity.c.project_id == project_id,
        entity.c.source_id == source_id,
        entity.c.table_name == name,
        entity.c.local_id == local_id,
    ]


async def resolve_references(
    session: AsyncSession, project_id: UUID, source_id: UUID, data: dict
) -> dict:
    """Replace local references with IDs owned by this project and source."""
    values = dict(data)
    for field, name in REFERENCES.items():
        if values.get(field) is None:
            continue
        target = (
            await session.execute(
                select(entity.c.central_id).where(
                    *get_identity(project_id, source_id, name, values[field]),
                )
            )
        ).scalar_one_or_none()
        if target is None:
            raise HTTPException(
                409, f"Send parent {name} before referencing it in {field}"
            )
        values[field] = target
    return values


async def save_entity(
    session: AsyncSession,
    settings: dict,
    source_id: UUID,
    item: CollectionEvent,
    data: dict,
) -> None:
    """Upsert a source-owned entity, ignoring snapshots older than its last one."""
    conditions = get_identity(settings["id"], source_id, item.table, item.local_id)
    mapping = (
        (await session.execute(select(entity).where(*conditions))).mappings().first()
    )
    if mapping and item.occurred_at <= mapping["observed_at"]:
        return
    table = TABLES[item.table]
    values = await resolve_references(session, settings["id"], source_id, data)
    if item.table == "collector_server":
        values["name"] = (
            f"{values['name']} [{settings['id']}/{source_id}/{item.local_id}]"
        )
        values["ingestion_project_id"] = settings["id"]
        if mapping is None:
            values.update(
                host=encrypt("remote-agent"),
                port=encrypt("5432"),
                username=encrypt(""),
                password=encrypt(""),
            )
    if item.table == "metadata_database":
        values["db_name"] = encrypt(values["db_name"])
    if mapping:
        await session.execute(
            update(table).where(table.c.id == mapping["central_id"]).values(**values)
        )
        await session.execute(
            update(entity).where(*conditions).values(observed_at=item.occurred_at)
        )
    else:
        central_id = (
            await session.execute(table.insert().values(**values).returning(table.c.id))
        ).scalar_one()
        await session.execute(
            entity.insert().values(
                project_id=settings["id"],
                source_id=source_id,
                table_name=item.table,
                local_id=item.local_id,
                central_id=central_id,
                observed_at=item.occurred_at,
            )
        )


async def save_observation(
    session: AsyncSession,
    settings: dict,
    source_id: UUID,
    item: CollectionEvent,
    data: dict,
) -> None:
    """Persist a metric or update an index-column relationship with mapped IDs."""
    table = TABLES[item.table]
    values = await resolve_references(session, settings["id"], source_id, data)
    if item.operation == "delete":
        await session.execute(
            table.delete().where(
                table.c.index_id == values["index_id"],
                table.c.column_id == values["column_id"],
            )
        )
    elif item.table == "metadata_index_column":
        await session.execute(
            insert(table)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[table.c.index_id, table.c.column_id],
                set_={"ordinal_position": values["ordinal_position"]},
            )
        )
    else:
        await session.execute(insert(table).values(**values).on_conflict_do_nothing())
