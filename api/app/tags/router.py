from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, status

from app.tags.models import TagCreate, TagUpdate, TagResponse
from app.tags import services
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection
from app.auth.services import get_current_user


router = APIRouter(
    prefix="/servers/{server_id}/tags",
    tags=["tags"],
    dependencies=[Depends(get_current_user)],
)

@router.post(
    "/",
    response_model=TagResponse,
    summary="Create a new tag",
    description="Creates a new classification tag scoped to a specific server.",
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": ErrorMessage, "description": "Server not found"},
        409: {"model": ErrorMessage, "description": "Tag already exists"},
        **COMMON_RESPONSES
    }
)
async def create_tag(server_id: UUID, tag_in: TagCreate):
    async with DatabaseConnection() as conn:
        return await services.create_tag(conn, server_id, tag_in)

@router.get(
    "/",
    response_model=List[TagResponse],
    summary="List all tags for a server",
    description="Returns all tags created for the specified server.",
    responses={
        404: {"model": ErrorMessage, "description": "Server not found"},
        **COMMON_RESPONSES
    }
)
async def list_tags(server_id: UUID):
    async with DatabaseConnection() as conn:
        return await services.list_tags(conn, server_id)

@router.patch(
    "/{tag_id}",
    response_model=TagResponse,
    summary="Update a tag",
    description="Updates the name or color of an existing tag.",
    responses={
        404: {"model": ErrorMessage, "description": "Tag not found"},
        409: {"model": ErrorMessage, "description": "Tag name already exists"},
        **COMMON_RESPONSES
    }
)
async def update_tag(server_id: UUID, tag_id: UUID, tag_in: TagUpdate):
    async with DatabaseConnection() as conn:
        return await services.update_tag(conn, server_id, tag_id, tag_in)

@router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tag",
    description="Deletes a tag. This will also remove the tag from any database objects it is attached to.",
    responses={
        404: {"model": ErrorMessage, "description": "Tag not found"},
        **COMMON_RESPONSES
    }
)
async def delete_tag(server_id: UUID, tag_id: UUID):
    async with DatabaseConnection() as conn:
        await services.delete_tag(conn, server_id, tag_id)
