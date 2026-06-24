from uuid import UUID

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.databases.metrics.services import database_metrics_stream
from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES


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
