from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schema.exceptions import DatabaseNotFoundError, SchemaFetchError
from app.schema.models import (
    SchemaResponse, SchemaTableResponse, SchemaColumnResponse, SchemaIndexResponse
)
from database.models.metadata import (
    Database, Table, ColumnModel, Index, IndexColumn
)


async def get_database_schema(db: AsyncSession, database_id: UUID) -> SchemaResponse:
    try:
        db_result = await db.execute(
            select(Database).where(Database.public_id == database_id, Database.deleted_at.is_(None))
        )
        database = db_result.scalar_one_or_none()

        if not database:
            raise DatabaseNotFoundError(str(database_id))

        tables_result = await db.execute(
            select(Table).where(Table.database_id == database.id, Table.deleted_at.is_(None))
        )
        tables = tables_result.scalars().all()
        table_ids = [t.id for t in tables]

        table_id_to_public = {t.id: t.public_id for t in tables}

        columns_result = await db.execute(
            select(ColumnModel).where(ColumnModel.table_id.in_(table_ids), ColumnModel.deleted_at.is_(None))
        )
        columns = columns_result.scalars().all()

        column_id_to_public = {c.id: c.public_id for c in columns}

        indexes_result = await db.execute(
            select(Index).where(Index.table_id.in_(table_ids), Index.deleted_at.is_(None))
        )
        indexes = indexes_result.scalars().all()
        index_ids = [i.id for i in indexes]

        index_columns_result = await db.execute(
            select(IndexColumn).where(IndexColumn.index_id.in_(index_ids))
        )
        index_columns = index_columns_result.scalars().all()

        index_cols_map = {}
        for ic in index_columns:
            index_cols_map.setdefault(ic.index_id, []).append(ic)

        column_id_to_name = {c.id: c.name for c in columns}

        table_responses = []
        for t in tables:
            t_columns = []
            for c in columns:
                if c.table_id == t.id:
                    fk_table_pub = table_id_to_public.get(c.fk_table_id) if c.fk_table_id else None
                    fk_col_pub = column_id_to_public.get(c.fk_column_id) if c.fk_column_id else None
                    
                    t_columns.append(SchemaColumnResponse(
                        id=c.public_id,
                        name=c.name,
                        description=c.description,
                        data_type=c.data_type,
                        is_nullable=c.is_nullable,
                        default_value=c.default_value,
                        is_unique=c.is_unique,
                        ordinal_position=c.ordinal_position,
                        fk_table_id=fk_table_pub,
                        fk_column_id=fk_col_pub
                    ))

            t_indexes = []
            for i in indexes:
                if i.table_id == t.id:
                    idx_cols = index_cols_map.get(i.id, [])
                    idx_cols.sort(key=lambda x: x.ordinal_position)
                    col_names = [column_id_to_name.get(ic.column_id, "unknown") for ic in idx_cols]
                    
                    t_indexes.append(SchemaIndexResponse(
                        id=i.public_id,
                        name=i.name,
                        type=i.type,
                        definition=i.definition,
                        is_unique=i.is_unique,
                        is_primary=i.is_primary,
                        columns=col_names
                    ))
            
            table_responses.append(SchemaTableResponse(
                id=t.public_id,
                schema_name=t.schema_name,
                name=t.name,
                description=t.description,
                columns=t_columns,
                indexes=t_indexes
            ))

        return SchemaResponse(
            id=database.public_id,
            tables=table_responses
        )
    except DatabaseNotFoundError:
        raise
    except Exception as e:
        raise SchemaFetchError(str(e))
