from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES, ErrorMessage
from app.servers.runs import services as run_services
from app.servers.runs.models import RunControlResult, RunHistoryItem, RunPatch
from database.connection import DatabaseConnection
from database.operations.collector import ServerRepository


router = APIRouter(
    prefix="/servers/{server_id}/runs",
    tags=["servers"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/stream",
    summary="SSE stream of server collector runs",
    description="Server-Sent Events endpoint that streams the current status of server-level collector runs. Updates every 2 seconds.",
    responses={
        404: {"model": ErrorMessage, "description": "Server not found"},
        **COMMON_RESPONSES,
    },
)
async def stream_server_runs(server_id: str):
    async with DatabaseConnection() as conn:
        server_repo = ServerRepository(conn)
        server = await server_repo.find_one_by(public_id=server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

    return EventSourceResponse(run_services.run_stream(server_id))


@router.get(
    "/history",
    response_model=List[RunHistoryItem],
    summary="List server run execution history",
    description="Returns execution history for server-level collector runs linked to a server.",
    responses={
        404: {"model": ErrorMessage, "description": "Server not found"},
        **COMMON_RESPONSES,
    },
)
async def get_server_run_history(
    server_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    async with DatabaseConnection() as conn:
        server_repo = ServerRepository(conn)
        server = await server_repo.find_one_by(public_id=server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

    return await run_services.list_run_history(server_id, limit=limit, offset=offset)


@router.patch(
    "/{run_id}",
    response_model=RunControlResult,
    summary="Control a server collector run",
    description="Controls a collector run by pausing, resuming, stopping, deleting or forcing execution.",
    responses={
        404: {"model": ErrorMessage, "description": "Server or run not found"},
        400: {"model": ErrorMessage, "description": "Invalid action or run type"},
        **COMMON_RESPONSES,
    },
)
async def patch_server_run(
    server_id: str,
    run_id: int,
    patch: RunPatch,
):
    async with DatabaseConnection() as conn:
        server_repo = ServerRepository(conn)
        server = await server_repo.find_one_by(public_id=server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

    try:
        result = await run_services.patch_run(run_id, "server", patch.action.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return RunControlResult.model_validate(result)
