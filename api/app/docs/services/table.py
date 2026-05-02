from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.docs.models import TableDocPut
from app.docs.services.common import resolve_object
from database.models.doc.table import TableDoc
from database.models.doc.object_tag import TableTag
from database.models.doc.tag import Tag
from database.operations.metadata.doc import TableDocRepository


async def put_table_doc(db: AsyncSession, database_id: UUID, table_id: int, doc_in: TableDocPut, user_id: int) -> TableDoc:
    repo = TableDocRepository(db)
    obj, _ = await resolve_object(db, "table", table_id)
    
    existing_doc = await repo.find_one_by(table_id=obj.id)
    
    if not existing_doc:
        new_doc = TableDoc(table_id=obj.id, **doc_in.model_dump(), updated_by=user_id)
        return await repo.insert(new_doc)
    else:
        update_data = doc_in.model_dump()
        update_data["updated_by"] = user_id
        return await repo.update(existing_doc.id, update_data)


async def get_table_doc(db: AsyncSession, database_id: UUID, table_id: int) -> dict:
    repo = TableDocRepository(db)
    obj, _ = await resolve_object(db, "table", table_id)
    
    doc = await repo.find_one_by(table_id=obj.id)
    if not doc:
        raise HTTPException(404, "Documentation not found")
        
    tags_query = select(Tag).join(TableTag).filter(TableTag.table_doc_id == doc.id)
    tags = (await db.execute(tags_query)).scalars().all()
    
    result = {c.name: getattr(doc, c.name) for c in doc.__table__.columns}
    result["tags"] = tags
    return result
