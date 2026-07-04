from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, Query, status

from app.tags.models import (
    TagAssignmentCreate,
    TagAssignmentDelete,
    TagAssignmentResponse,
    TagCreate,
    TagResponse,
    TagUpdate,
)
from app.tags import services
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection
from app.auth.services import get_current_user


router = APIRouter(
    prefix="/tags",
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
async def create_tag(tag_in: TagCreate):
    async with DatabaseConnection() as conn:
        return await services.create_tag(conn, tag_in)

@router.get(
    "/",
    response_model=List[TagResponse],
    summary="List all tags",
    description="Returns all classification tags.",
    responses={
        404: {"model": ErrorMessage, "description": "Server not found"},
        **COMMON_RESPONSES
    }
)
async def list_tags(server_id: UUID | None = Query(default=None)):
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
async def update_tag(tag_id: UUID, tag_in: TagUpdate):
    async with DatabaseConnection() as conn:
        return await services.update_tag(conn, tag_id, tag_in)

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
async def delete_tag(tag_id: UUID):
    async with DatabaseConnection() as conn:
        await services.delete_tag(conn, tag_id)

@router.get(
    "/assignments",
    response_model=List[TagAssignmentResponse],
    summary="List tag assignments",
    description="Returns tag assignments for direct database objects and documentation records.",
    responses={**COMMON_RESPONSES}
)
async def list_assignments(database_id: UUID | None = Query(default=None)):
    async with DatabaseConnection() as conn:
        return await services.list_assignments(conn, database_id)

@router.post(
    "/{tag_id}/assignments",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Attach a tag",
    description="Attaches a tag to a direct metadata object or to a documentation record.",
    responses={
        404: {"model": ErrorMessage, "description": "Tag or target not found"},
        **COMMON_RESPONSES
    }
)
async def attach_tag(tag_id: UUID, assignment: TagAssignmentCreate):
    async with DatabaseConnection() as conn:
        await services.attach_tag(conn, tag_id, assignment)

@router.api_route(
    "/{tag_id}/assignments",
    methods=["DELETE"],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a tag",
    description="Detaches a tag from a direct metadata object or from a documentation record.",
    responses={
        404: {"model": ErrorMessage, "description": "Tag or target not found"},
        **COMMON_RESPONSES
    }
)
async def detach_tag(tag_id: UUID, assignment: TagAssignmentDelete):
    async with DatabaseConnection() as conn:
        await services.detach_tag(conn, tag_id, assignment)
