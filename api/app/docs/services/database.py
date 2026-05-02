from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.docs.models import DatabaseDocPut
from app.docs.services.common import resolve_object
from database.models.doc.database import DatabaseDoc
from database.models.doc.object_tag import DatabaseTag
from database.models.doc.tag import Tag
from database.operations.metadata.doc import DatabaseDocRepository


async def put_database_doc(db: AsyncSession, database_id: UUID, doc_in: DatabaseDocPut, user_id: int) -> DatabaseDoc:
    repo = DatabaseDocRepository(db)
    obj, _ = await resolve_object(db, "database", database_id)
    
    existing_doc = await repo.find_one_by(database_id=obj.id)
    
    if not existing_doc:
        new_doc = DatabaseDoc(database_id=obj.id, **doc_in.model_dump(), updated_by=user_id)
        return await repo.insert(new_doc)
    else:
        update_data = doc_in.model_dump()
        update_data["updated_by"] = user_id
        return await repo.update(existing_doc.id, update_data)


async def get_database_doc(db: AsyncSession, database_id: UUID) -> dict:
    repo = DatabaseDocRepository(db)
    obj, _ = await resolve_object(db, "database", database_id)
    
    doc = await repo.find_one_by(database_id=obj.id)
    if not doc:
        raise HTTPException(404, "Documentation not found")
        
    tags_query = select(Tag).join(DatabaseTag).filter(DatabaseTag.database_doc_id == doc.id)
    tags = (await db.execute(tags_query)).scalars().all()
    
    result = {c.name: getattr(doc, c.name) for c in doc.__table__.columns}
    result["tags"] = tags
    return result
