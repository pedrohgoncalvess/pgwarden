from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.databases.docs.models import DatabaseDocPut
from app.databases.docs.services.common import resolve_object
from app.databases.docs.services.embeddings import build_database_embedding_text
from database.models.doc.database import DatabaseDoc
from database.models.doc.object_tag import DatabaseDocTag
from database.models.doc.tag import Tag
from database.operations.metadata.doc import DatabaseDocRepository
from utils import decrypt_or_plain
from utils.embeddings import generate_embedding_cached


async def put_database_doc(db: AsyncSession, database_id: UUID, doc_in: DatabaseDocPut, user_id: int) -> DatabaseDoc:
    repo = DatabaseDocRepository(db)
    obj, _ = await resolve_object(db, "database", database_id)

    existing_doc = await repo.find_one_by(database_id=obj.id)

    db_name = decrypt_or_plain(obj.db_name)
    doc_or_data = existing_doc or DatabaseDoc(database_id=obj.id, **doc_in.model_dump())
    embedding_text = build_database_embedding_text(obj, db_name, doc_or_data)
    embedding = await generate_embedding_cached(db, embedding_text)

    if not existing_doc:
        new_doc = DatabaseDoc(
            database_id=obj.id,
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


async def get_database_doc(db: AsyncSession, database_id: UUID) -> dict:
    repo = DatabaseDocRepository(db)
    obj, _ = await resolve_object(db, "database", database_id)
    
    doc = await repo.find_one_by(database_id=obj.id)
    if not doc:
        raise HTTPException(404, "Documentation not found")
        
    tags_query = select(Tag).join(DatabaseDocTag).filter(DatabaseDocTag.database_doc_id == doc.id)
    tags = (await db.execute(tags_query)).scalars().all()
    
    result = {c.name: getattr(doc, c.name) for c in doc.__table__.columns if c.name != "embedding"}
    result["tags"] = tags
    return result
