from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.databases.analytics.models import AnalyticsDataResponse
from app.databases.analytics import services
from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection


router = APIRouter(
    prefix="/databases/{database_id}/analytics",
    tags=["databases"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/data",
    response_model=AnalyticsDataResponse,
    summary="Get database and table size analytics",
    description="Returns historical size data for the database and its tables, filtered by date range and selected tables.",
    responses={
        404: {"model": ErrorMessage, "description": "Database not found"},
        **COMMON_RESPONSES
    }
)
async def get_analytics_data(
    database_id: UUID,
    start_date: Optional[str] = Query(default=None, description="Start date in ISO 8601 format"),
    end_date: Optional[str] = Query(default=None, description="End date in ISO 8601 format"),
    preset: Optional[str] = Query(default="1w", description="Preset range: 1d, 3d, 1w, 2w, 1m"),
    table_ids: Optional[List[int]] = Query(default=None, description="Filter by specific table IDs"),
):
    async with DatabaseConnection() as conn:
        return await services.get_analytics_data(
            conn, database_id, start_date, end_date, preset, table_ids
        )
