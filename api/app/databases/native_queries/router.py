from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sse_starlette.sse import EventSourceResponse

from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES
from app.databases.native_queries.services import list_native_queries, native_query_stream


router = APIRouter(
    prefix="/databases/{database_id}/native-queries",
    tags=["native queries"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "",
    summary="List recent native query samples",
    description="Returns recent pg_stat_activity query samples collected into metric.native_query.",
    responses=COMMON_RESPONSES,
)
async def list_recent_native_queries(database_id: UUID, limit: int = Query(default=100, ge=1, le=1000)):
    return await list_native_queries(database_id, limit)


@router.get(
    "/stream",
    summary="SSE stream of native query samples",
    description="Streams the latest pg_stat_activity query samples collected into metric.native_query.",
    responses=COMMON_RESPONSES,
)
async def stream_native_queries(database_id: UUID):
    return EventSourceResponse(native_query_stream(database_id))
