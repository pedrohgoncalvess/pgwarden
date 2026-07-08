from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.databases.analytics.query.models import QueryAnalyticsResponse
from app.databases.analytics.query import services
from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection


router = APIRouter(
    prefix="/databases/{database_id}/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/query",
    response_model=QueryAnalyticsResponse,
    summary="Get query analytics",
    description="Returns aggregated query analytics from native_query snapshots, with normalization, KPIs, filters and timeline.",
    responses={
        404: {"model": ErrorMessage, "description": "Database not found"},
        **COMMON_RESPONSES
    }
)
async def get_query_analytics(
    database_id: UUID,
    start_date: Optional[str] = Query(default=None, description="Start date in ISO 8601 format"),
    end_date: Optional[str] = Query(default=None, description="End date in ISO 8601 format"),
    preset: Optional[str] = Query(default="1w", description="Preset range: 1d, 3d, 1w, 2w, 1m, custom"),
    user_name: Optional[str] = Query(default=None, description="Filter by database user"),
    application_name: Optional[str] = Query(default=None, description="Filter by application name"),
    state: Optional[str] = Query(default=None, description="Filter by query state"),
    search: Optional[List[str]] = Query(default=None, description="Search terms within the normalized query signature. Repeated values are OR-ed."),
    exclude: Optional[List[str]] = Query(default=None, description="Exclude queries whose signature contains any of these terms"),
    limit: Optional[int] = Query(default=50, ge=1, le=500, description="Maximum number of query signatures to return"),
):
    async with DatabaseConnection() as conn:
        return await services.get_query_analytics(
            conn,
            database_id,
            start_date,
            end_date,
            preset,
            user_name,
            application_name,
            state,
            search,
            exclude,
            limit,
        )
