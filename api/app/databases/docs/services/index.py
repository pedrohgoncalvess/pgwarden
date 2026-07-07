from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.docs.models import IndexDocPut
from app.databases.docs.services.common import resolve_object
from app.databases.docs.services.embeddings import build_index_embedding_text
from database.models.doc.index import IndexDoc
from database.models.doc.object_tag import IndexDocTag
from database.models.doc.tag import Tag
from database.models.metadata.table import Table
from database.operations.metadata.doc import IndexDocRepository
from utils.embeddings import generate_embedding


async def put_index_doc(db: AsyncSession, database_id: UUID, index_id: int, doc_in: IndexDocPut, user_id: int) -> IndexDoc:
    repo = IndexDocRepository(db)
    obj, _ = await resolve_object(db, "index", index_id)

    existing_doc = await repo.find_one_by(index_id=obj.id)

    table = await _load_index_table(db, obj.table_id)
    doc_or_data = existing_doc or IndexDoc(index_id=obj.id, **doc_in.model_dump())
    embedding_text = build_index_embedding_text(obj, table, doc_or_data)
    embedding = await generate_embedding(embedding_text)

    if not existing_doc:
        new_doc = IndexDoc(
            index_id=obj.id,
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


async def _load_index_table(db: AsyncSession, table_id: int) -> Table:
    result = await db.execute(select(Table).where(Table.id == table_id))
    return result.scalar_one()


async def get_index_doc(db: AsyncSession, database_id: UUID, index_id: int) -> dict:
    repo = IndexDocRepository(db)
    obj, _ = await resolve_object(db, "index", index_id)
    
    doc = await repo.find_one_by(index_id=obj.id)
    if not doc:
        raise HTTPException(404, "Documentation not found")
        
    tags_query = select(Tag).join(IndexDocTag).filter(IndexDocTag.index_doc_id == doc.id)
    tags = (await db.execute(tags_query)).scalars().all()
    
    result = {c.name: getattr(doc, c.name) for c in doc.__table__.columns if c.name != "embedding"}
    result["tags"] = tags
    return result
