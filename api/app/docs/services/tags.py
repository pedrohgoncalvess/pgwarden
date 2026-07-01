from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.tags.models import TagAssignmentCreate, TagAssignmentDelete
from app.tags.services import attach_tag as attach_tag_assignment
from app.tags.services import detach_tag as detach_tag_assignment


async def attach_tag(
    db: AsyncSession,
    tag_id: UUID,
    scope: str,
    target_type: str,
    target_id: UUID | None = None,
    database_id: UUID | None = None,
    schema_name: str | None = None,
    query_hash: str | None = None,
) -> None:
    assignment = TagAssignmentCreate(
        scope=scope,
        target_type=target_type,
        target_id=target_id,
        database_id=database_id,
        schema_name=schema_name,
        query_hash=query_hash,
    )
    await attach_tag_assignment(db, tag_id, assignment)


async def detach_tag(
    db: AsyncSession,
    tag_id: UUID,
    scope: str,
    target_type: str,
    target_id: UUID | None = None,
    database_id: UUID | None = None,
    schema_name: str | None = None,
    query_hash: str | None = None,
) -> None:
    assignment = TagAssignmentDelete(
        scope=scope,
        target_type=target_type,
        target_id=target_id,
        database_id=database_id,
        schema_name=schema_name,
        query_hash=query_hash,
    )
    await detach_tag_assignment(db, tag_id, assignment)
