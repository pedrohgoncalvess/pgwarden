from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.docs.models import IndexDocPut
from app.docs.services.common import resolve_object
from database.models.doc.index import IndexDoc
from database.models.doc.object_tag import IndexTag
from database.models.doc.tag import Tag
from database.operations.metadata.doc import IndexDocRepository


async def put_index_doc(db: AsyncSession, database_id: UUID, index_id: int, doc_in: IndexDocPut, user_id: int) -> IndexDoc:
    repo = IndexDocRepository(db)
    obj, _ = await resolve_object(db, "index", index_id)
    
    existing_doc = await repo.find_one_by(index_id=obj.id)
    
    if not existing_doc:
        new_doc = IndexDoc(index_id=obj.id, **doc_in.model_dump(), updated_by=user_id)
        return await repo.insert(new_doc)
    else:
        update_data = doc_in.model_dump()
        update_data["updated_by"] = user_id
        return await repo.update(existing_doc.id, update_data)


async def get_index_doc(db: AsyncSession, database_id: UUID, index_id: int) -> dict:
    repo = IndexDocRepository(db)
    obj, _ = await resolve_object(db, "index", index_id)
    
    doc = await repo.find_one_by(index_id=obj.id)
    if not doc:
        raise HTTPException(404, "Documentation not found")
        
    tags_query = select(Tag).join(IndexTag).filter(IndexTag.index_doc_id == doc.id)
    tags = (await db.execute(tags_query)).scalars().all()
    
    result = {c.name: getattr(doc, c.name) for c in doc.__table__.columns}
    result["tags"] = tags
    return result
