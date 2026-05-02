from uuid import UUID
from typing import Tuple, Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database.operations.metadata.database import DatabaseRepository
from database.operations.metadata.table import TableRepository
from database.operations.metadata.column import ColumnRepository
from database.operations.metadata.index import IndexRepository


async def resolve_object(db: AsyncSession, object_type: str, public_id: UUID) -> Tuple[Any, Any]:
    if object_type == "database":
        repo = DatabaseRepository(db)
        obj = await repo.find_one_by(public_id=public_id)
        if not obj:
            raise HTTPException(404, "Database not found")
        return obj, obj.id
    elif object_type == "table":
        repo = TableRepository(db)
        obj = await repo.find_one_by(public_id=public_id)
        if not obj:
            raise HTTPException(404, "Table not found")
        return obj, obj.database_id
    elif object_type == "column":
        repo = ColumnRepository(db)
        obj = await repo.find_one_by(public_id=public_id)
        if not obj:
            raise HTTPException(404, "Column not found")
        
        table_repo = TableRepository(db)
        table = await table_repo.find_by_id(obj.table_id)
        return obj, table.database_id
    elif object_type == "index":
        repo = IndexRepository(db)
        obj = await repo.find_one_by(public_id=public_id)
        if not obj:
            raise HTTPException(404, "Index not found")
        return obj, obj.database_id
    else:
        raise ValueError("Invalid object type")
