from fastapi import APIRouter, Depends
from uuid import UUID

from app.databases.models import DatabaseStatsResponse
from app.databases.stats.services import get_database_stats
from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection


router = APIRouter(
    prefix="/databases/{database_id}/stats",
    tags=["databases"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/",
    response_model=DatabaseStatsResponse,
    summary="Get database statistics overview",
    description="Returns aggregated statistics for a database: table count, index count, view count, "
                "database size (bytes), and index hit rate (calculated from the latest pg_stat_database snapshot).",
    responses={
        404: {"model": ErrorMessage, "description": "Database not found"},
        **COMMON_RESPONSES
    }
)
async def get_stats(database_id: UUID):
    async with DatabaseConnection() as conn:
        return await get_database_stats(conn, database_id)
