from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.schemas.history.models import SchemaHistoryResponse
from app.schemas.history.services import get_database_schema_history
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection
from app.auth.services import get_current_user


router = APIRouter(
    prefix="/schemas",
    tags=["schemas"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/{database_id}/history",
    response_model=SchemaHistoryResponse,
    summary="Get database schema change history",
    description=(
        "Returns a timeline of schema changes for the requested database: "
        "table/column/index additions, removals (soft deletes) and alterations. "
        "Results are ordered from newest to oldest."
    ),
    responses={
        404: {"model": ErrorMessage, "description": "Database not found"},
        **COMMON_RESPONSES
    }
)
async def get_schema_history(
    database_id: UUID,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return"),
    offset: int = Query(0, ge=0, description="Number of events to skip"),
    table_id: UUID | None = Query(None, description="Filter events to a specific table"),
):
    async with DatabaseConnection() as conn:
        return await get_database_schema_history(
            conn, database_id, limit=limit, offset=offset, table_id=table_id
        )
