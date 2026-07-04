from uuid import UUID

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.databases.metrics.services import database_metrics_stream
from app.databases.metrics.stats import get_database_stats
from app.databases.metrics.uptime import get_database_uptime
from app.databases.models import (
    DatabaseMetricsSummaryResponse,
    DatabaseStatsResponse,
    UptimeResponse,
)
from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection


router = APIRouter(
    prefix="/databases/{database_id}/metrics",
    tags=["databases"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/stream",
    summary="SSE stream of database metrics",
    description="Server-Sent Events endpoint that streams TPS (transactions per second) for a specific database. "
                "Calculates the delta between the two most recent pg_stat_database snapshots. "
                "Polls every 2 seconds.",
    responses=COMMON_RESPONSES
)
async def stream_database_metrics(database_id: UUID):
    return EventSourceResponse(database_metrics_stream(database_id))


@router.get(
    "/stats",
    response_model=DatabaseStatsResponse,
    summary="Get database statistics overview",
    description="Returns aggregated statistics for a database: table count, index count, view count, database size and index hit rate.",
    responses={
        404: {"model": ErrorMessage, "description": "Database not found"},
        **COMMON_RESPONSES,
    },
)
async def get_stats(database_id: UUID):
    async with DatabaseConnection() as conn:
        return await get_database_stats(conn, database_id)


@router.get(
    "/uptime",
    response_model=UptimeResponse,
    summary="Get database uptime",
    description="Returns the uptime of the PostgreSQL server hosting the database.",
    responses={
        404: {"model": ErrorMessage, "description": "Database not found"},
        **COMMON_RESPONSES,
    },
)
async def get_uptime(database_id: UUID):
    async with DatabaseConnection() as conn:
        return await get_database_uptime(conn, database_id)


@router.get(
    "/summary",
    response_model=DatabaseMetricsSummaryResponse,
    summary="Get database metrics summary",
    description="Returns database stats and uptime in one response for overview screens.",
    responses={
        404: {"model": ErrorMessage, "description": "Database not found"},
        **COMMON_RESPONSES,
    },
)
async def get_metrics_summary(database_id: UUID):
    async with DatabaseConnection() as conn:
        stats = await get_database_stats(conn, database_id)
        uptime = await get_database_uptime(conn, database_id)
        return DatabaseMetricsSummaryResponse(
            database_id=database_id,
            stats=stats,
            uptime=uptime,
        )
