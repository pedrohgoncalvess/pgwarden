from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.schemas.history.exceptions import HistoryDatabaseNotFoundError, HistoryFetchError
from app.databases.schemas.history.models import SchemaHistoryResponse, SchemaHistoryItem
from database.models.metadata import (
    Database, Table, ColumnModel, Index,
    TableHistory, ColumnHistory, IndexHistory
)


def _table_diff(history: TableHistory, current: Table | None) -> str | None:
    if current is None:
        return "Previous table state recorded"

    changes = []
    if history.schema_name != current.schema_name:
        changes.append(f"schema_name changed from '{history.schema_name}' to '{current.schema_name}'")
    if history.name != current.name:
        changes.append(f"name changed from '{history.name}' to '{current.name}'")
    if history.description != current.description:
        changes.append(
            f"description changed from '{history.description}' to '{current.description}'"
        )

    return "; ".join(changes) if changes else None


def _column_diff(
    history: ColumnHistory,
    current: ColumnModel | None,
    tables: dict[int, Table],
    columns: dict[int, ColumnModel],
) -> str | None:
    if current is None:
        return "Previous column state recorded"

    changes = []
    fields = [
        ("name", history.name, current.name),
        ("description", history.description, current.description),
        ("data_type", history.data_type, current.data_type),
        ("is_nullable", history.is_nullable, current.is_nullable),
        ("default_value", history.default_value, current.default_value),
        ("is_unique", history.is_unique, current.is_unique),
        ("ordinal_position", history.ordinal_position, current.ordinal_position),
    ]
    for label, old, new in fields:
        if old != new:
            changes.append(f"{label} changed from '{old}' to '{new}'")

    old_fk_table = (
        tables[history.fk_table_id].name
        if history.fk_table_id and history.fk_table_id in tables
        else history.fk_table_id
    )
    new_fk_table = (
        tables[current.fk_table_id].name
        if current.fk_table_id and current.fk_table_id in tables
        else current.fk_table_id
    )
    if old_fk_table != new_fk_table:
        changes.append(f"fk_table changed from '{old_fk_table}' to '{new_fk_table}'")

    old_fk_column = (
        columns[history.fk_column_id].name
        if history.fk_column_id and history.fk_column_id in columns
        else history.fk_column_id
    )
    new_fk_column = (
        columns[current.fk_column_id].name
        if current.fk_column_id and current.fk_column_id in columns
        else current.fk_column_id
    )
    if old_fk_column != new_fk_column:
        changes.append(f"fk_column changed from '{old_fk_column}' to '{new_fk_column}'")

    return "; ".join(changes) if changes else None


def _index_diff(history: IndexHistory, current: Index | None) -> str | None:
    if current is None:
        return "Previous index state recorded"

    changes = []
    fields = [
        ("name", history.name, current.name),
        ("type", history.type, current.type),
        ("definition", history.definition, current.definition),
        ("is_unique", history.is_unique, current.is_unique),
        ("is_primary", history.is_primary, current.is_primary),
    ]
    for label, old, new in fields:
        if old != new:
            changes.append(f"{label} changed from '{old}' to '{new}'")

    return "; ".join(changes) if changes else None


async def get_database_schema_history(
    db: AsyncSession,
    database_id: UUID,
    limit: int = 100,
    offset: int = 0,
    table_id: UUID | None = None,
) -> SchemaHistoryResponse:
    try:
        db_result = await db.execute(
            select(Database).where(Database.public_id == database_id, Database.deleted_at.is_(None))
        )
        database = db_result.scalar_one_or_none()

        if not database:
            raise HistoryDatabaseNotFoundError(str(database_id))

        tables_result = await db.execute(
            select(Table).where(Table.database_id == database.id)
        )
        tables = tables_result.scalars().all()

        if table_id is not None:
            tables = [t for t in tables if t.public_id == table_id]

        table_by_id: dict[int, Table] = {t.id: t for t in tables}
        table_ids = list(table_by_id.keys())

        columns_result = await db.execute(
            select(ColumnModel).where(ColumnModel.table_id.in_(table_ids))
        )
        columns = columns_result.scalars().all()
        column_by_id: dict[int, ColumnModel] = {c.id: c for c in columns}
        column_ids = list(column_by_id.keys())

        indexes_result = await db.execute(
            select(Index).where(Index.table_id.in_(table_ids))
        )
        indexes = indexes_result.scalars().all()
        index_by_id: dict[int, Index] = {i.id: i for i in indexes}
        index_ids = list(index_by_id.keys())

        table_history_result = await db.execute(
            select(TableHistory).where(TableHistory.table_id.in_(table_ids))
        )
        table_history = table_history_result.scalars().all()

        column_history_result = await db.execute(
            select(ColumnHistory).where(ColumnHistory.column_id.in_(column_ids))
        )
        column_history = column_history_result.scalars().all()

        index_history_result = await db.execute(
            select(IndexHistory).where(IndexHistory.index_id.in_(index_ids))
        )
        index_history = index_history_result.scalars().all()

        events: list[SchemaHistoryItem] = []

        for t in tables:
            if t.deleted_at is not None:
                events.append(SchemaHistoryItem(
                    id=str(t.public_id),
                    type="table",
                    action="removed",
                    schema_name=t.schema_name,
                    table_name=t.name,
                    object_id=t.public_id,
                    changed_at=t.deleted_at,
                    changed_by=t.deleted_by,
                    details=f"Table {t.schema_name}.{t.name} removed",
                ))

        for th in table_history:
            current = table_by_id.get(th.table_id)
            details = _table_diff(th, current)
            if not details:
                continue
            events.append(SchemaHistoryItem(
                id=str(th.id),
                type="table",
                action="altered",
                schema_name=th.schema_name,
                table_name=th.name,
                object_id=current.public_id if current else None,
                changed_at=th.changed_at,
                changed_by=th.changed_by,
                details=details,
            ))

        for c in columns:
            table = table_by_id.get(c.table_id)
            if c.deleted_at is None:
                if table and c.created_at > (table.created_at + timedelta(minutes=1)):
                    events.append(SchemaHistoryItem(
                        id=str(c.public_id),
                        type="column",
                        action="added",
                        schema_name=table.schema_name,
                        table_name=table.name,
                        column_name=c.name,
                        object_id=c.public_id,
                        table_id=table.public_id,
                        changed_at=c.created_at,
                        changed_by=c.created_by,
                        details=f"Column {c.name} added to {table.schema_name}.{table.name}",
                    ))
            else:
                events.append(SchemaHistoryItem(
                    id=str(c.public_id),
                    type="column",
                    action="removed",
                    schema_name=table.schema_name if table else None,
                    table_name=table.name if table else None,
                    column_name=c.name,
                    object_id=c.public_id,
                    table_id=table.public_id if table else None,
                    changed_at=c.deleted_at,
                    changed_by=c.deleted_by,
                    details=(
                        f"Column {c.name} removed from {table.schema_name}.{table.name}"
                        if table else f"Column {c.name} removed"
                    ),
                ))

        for ch in column_history:
            current = column_by_id.get(ch.column_id)
            details = _column_diff(ch, current, table_by_id, column_by_id)
            if not details:
                continue
            table = table_by_id.get(ch.table_id) or (current and table_by_id.get(current.table_id))
            events.append(SchemaHistoryItem(
                id=str(ch.id),
                type="column",
                action="altered",
                schema_name=table.schema_name if table else None,
                table_name=table.name if table else None,
                column_name=ch.name,
                object_id=current.public_id if current else None,
                table_id=table.public_id if table else None,
                changed_at=ch.changed_at,
                changed_by=ch.changed_by,
                details=details,
            ))

        for i in indexes:
            table = table_by_id.get(i.table_id)
            if i.deleted_at is None:
                if table and i.created_at > (table.created_at + timedelta(minutes=1)):
                    events.append(SchemaHistoryItem(
                        id=str(i.public_id),
                        type="index",
                        action="added",
                        schema_name=table.schema_name,
                        table_name=table.name,
                        index_name=i.name,
                        object_id=i.public_id,
                        table_id=table.public_id,
                        changed_at=i.created_at,
                        changed_by=i.created_by,
                        details=f"Index {i.name} added to {table.schema_name}.{table.name}",
                    ))
            else:
                events.append(SchemaHistoryItem(
                    id=str(i.public_id),
                    type="index",
                    action="removed",
                    schema_name=table.schema_name if table else None,
                    table_name=table.name if table else None,
                    index_name=i.name,
                    object_id=i.public_id,
                    table_id=table.public_id if table else None,
                    changed_at=i.deleted_at,
                    changed_by=i.deleted_by,
                    details=(
                        f"Index {i.name} removed from {table.schema_name}.{table.name}"
                        if table else f"Index {i.name} removed"
                    ),
                ))

        for ih in index_history:
            current = index_by_id.get(ih.index_id)
            details = _index_diff(ih, current)
            if not details:
                continue
            table = table_by_id.get(ih.table_id) or (current and table_by_id.get(current.table_id))
            events.append(SchemaHistoryItem(
                id=str(ih.id),
                type="index",
                action="altered",
                schema_name=table.schema_name if table else None,
                table_name=table.name if table else None,
                index_name=ih.name,
                object_id=current.public_id if current else None,
                table_id=table.public_id if table else None,
                changed_at=ih.changed_at,
                changed_by=ih.changed_by,
                details=details,
            ))

        events.sort(key=lambda e: e.changed_at, reverse=True)
        total = len(events)
        paginated = events[offset:offset + limit]

        return SchemaHistoryResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=paginated,
        )
    except HistoryDatabaseNotFoundError:
        raise
    except Exception as e:
        raise HistoryFetchError(str(e))
