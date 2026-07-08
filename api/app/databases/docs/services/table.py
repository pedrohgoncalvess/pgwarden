from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.docs.models import TableDocPut
from app.databases.docs.services.common import resolve_object
from app.databases.docs.services.embeddings import build_table_embedding_text
from database.models.doc.table import TableDoc
from database.models.doc.object_tag import TableDocTag
from database.models.doc.tag import Tag
from database.models.metadata.column import ColumnModel
from database.operations.metadata.doc import TableDocRepository
from utils.embeddings import generate_embedding_cached


async def put_table_doc(db: AsyncSession, database_id: UUID, table_id: int, doc_in: TableDocPut, user_id: int) -> TableDoc:
    repo = TableDocRepository(db)
    obj, _ = await resolve_object(db, "table", table_id)

    existing_doc = await repo.find_one_by(table_id=obj.id)

    columns = await _load_table_columns(db, obj.id)
    doc_or_data = existing_doc or TableDoc(table_id=obj.id, **doc_in.model_dump())
    embedding_text = build_table_embedding_text(obj, columns, doc_or_data)
    embedding = await generate_embedding_cached(db, embedding_text)

    if not existing_doc:
        new_doc = TableDoc(
            table_id=obj.id,
            **doc_in.model_dump(),
            updated_by=user_id,
            embedding=embedding,
        )
        return await repo.insert(new_doc)
    else:
        update_data = doc_in.model_dump()
        update_data["updated_by"] = user_id
        update_data["embedding"] = embedding
        return await repo.update(existing_doc.id, update_data)


async def _load_table_columns(db: AsyncSession, table_id: int) -> list[ColumnModel]:
    result = await db.execute(
        select(ColumnModel)
        .where(ColumnModel.table_id == table_id)
        .order_by(ColumnModel.ordinal_position)
    )
    return list(result.scalars().all())


async def get_table_doc(db: AsyncSession, database_id: UUID, table_id: int) -> dict:
    repo = TableDocRepository(db)
    obj, _ = await resolve_object(db, "table", table_id)
    
    doc = await repo.find_one_by(table_id=obj.id)
    if not doc:
        raise HTTPException(404, "Documentation not found")
        
    tags_query = select(Tag).join(TableDocTag).filter(TableDocTag.table_doc_id == doc.id)
    tags = (await db.execute(tags_query)).scalars().all()
    
    result = {c.name: getattr(doc, c.name) for c in doc.__table__.columns if c.name != "embedding"}
    result["tags"] = tags
    return result
