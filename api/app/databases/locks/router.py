from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.databases.locks.services import lock_stream
from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES


router = APIRouter(
    prefix="/databases/{database_id}/locks",
    tags=["locks"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/stream",
    summary="SSE stream of active locks",
    description="Server-Sent Events endpoint that streams the latest collected locks for a specific database. Updates every 3 seconds.",
    responses=COMMON_RESPONSES
)
async def stream_locks(database_id: int):
    return EventSourceResponse(lock_stream(database_id))
