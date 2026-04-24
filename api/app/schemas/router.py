from uuid import UUID

from fastapi import APIRouter, Depends

from app.schemas.models import SchemaResponse
from app.schemas.services import get_database_schema
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection
from app.auth.services import get_current_user


router = APIRouter(
    prefix="/schemas",
    tags=["schema"],
    dependencies=[Depends(get_current_user)],
)

@router.get(
    "/{database_id}",
    response_model=SchemaResponse,
    summary="Get database schema metadata",
    description="Returns the full, tracked schema definition of the requested database. This includes tables, columns, constraints, and indexes. Does NOT return actual table data.",
    responses={
        404: {"model": ErrorMessage, "description": "Database not found"},
        **COMMON_RESPONSES
    }
)
async def get_schema(database_id: UUID):
    async with DatabaseConnection() as conn:
        return await get_database_schema(conn, database_id)
