from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.servers.metrics.services import server_metrics_stream
from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES


router = APIRouter(
    prefix="/servers/{server_id}/metrics",
    tags=["servers"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/stream",
    summary="SSE stream of server metrics",
    description="Server-Sent Events endpoint that streams CPU, RAM, disk, and I/O metrics for a specific server. "
                "Each metric type is emitted as a separate event (cpu, ram, disk, io) only when new data is available. "
                "Polls every 2 seconds, adapting to each collector's configured interval.",
    responses=COMMON_RESPONSES
)
async def stream_server_metrics(server_id: int):
    return EventSourceResponse(server_metrics_stream(server_id))
