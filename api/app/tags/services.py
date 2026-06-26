from uuid import UUID
from typing import List
from fastapi import HTTPException

from sqlalchemy.ext.asyncio import AsyncSession

from database.operations.metadata.tag import TagRepository
from database.operations.collector.server import ServerRepository
from database.models.doc.tag import Tag
from app.tags.models import TagCreate, TagUpdate


async def create_tag(db: AsyncSession, tag_in: TagCreate) -> Tag:
    tag_repo = TagRepository(db)

    new_tag = Tag(
        name=tag_in.name,
        description=tag_in.description,
        color=tag_in.color
    )

    try:
        return await tag_repo.insert(new_tag)
    except ValueError as e:
        if "UniqueConstraint" in str(e) or "UniqueViolationError" in str(e) or "duplicate key" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Tag '{tag_in.name}' already exists for this server")
        raise HTTPException(status_code=400, detail=str(e))


async def list_tags(db: AsyncSession) -> List[Tag]:
    tag_repo = TagRepository(db)

    return await tag_repo.find_all()


async def update_tag(db: AsyncSession, tag_id: UUID, tag_in: TagUpdate) -> Tag:
    tag_repo = TagRepository(db)
    
    tag = await tag_repo.find_one_by(public_id=tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    if tag_in.name and tag_in.name != tag.name:
        existing = await tag_repo.find_one_by(server_id=tag.server_id, name=tag_in.name)
        if existing:
            raise HTTPException(status_code=409, detail=f"Tag '{tag_in.name}' already exists for this server")

    update_data = tag_in.model_dump(exclude_unset=True)
    if not update_data:
        return tag

    return await tag_repo.update(tag.id, update_data)


async def delete_tag(db: AsyncSession, tag_id: UUID) -> None:
    tag_repo = TagRepository(db)
    
    tag = await tag_repo.find_one_by(public_id=tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    await tag_repo.delete(tag.id)
