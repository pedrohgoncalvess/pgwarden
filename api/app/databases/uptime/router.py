from fastapi import APIRouter, Depends
from uuid import UUID

from app.databases.models import UptimeResponse
from app.databases.uptime.services import get_database_uptime
from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection


router = APIRouter(
    prefix="/databases/{database_id}/uptime",
    tags=["databases"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/",
    response_model=UptimeResponse,
    summary="Get database uptime",
    description="Returns the uptime of the PostgreSQL server hosting the database. "
                "Connects directly to the monitored database to query pg_postmaster_start_time(). "
                "Formats the uptime as days/hours/minutes or just hours/minutes/minutes.",
    responses={
        404: {"model": ErrorMessage, "description": "Database not found"},
        **COMMON_RESPONSES
    }
)
async def get_uptime(database_id: UUID):
    async with DatabaseConnection() as conn:
        return await get_database_uptime(conn, database_id)
