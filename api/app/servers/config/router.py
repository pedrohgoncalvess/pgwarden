from typing import List

from fastapi import APIRouter, HTTPException, Depends, Query
from sse_starlette.sse import EventSourceResponse

from app.servers.config.models import (
    ConfigItem, ConfigPatch,
    RunPatch, RunHistoryItem,
    RunControlResult, RunType
)
from app.servers.config import services as run_services
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection
from database.operations.collector import ConfigServerRepository, ServerRepository
from app.auth.services import get_current_user


router = APIRouter(
    prefix="/servers/{server_id}/configs",
    tags=["servers"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/",
    response_model=List[ConfigItem],
    summary="List collector configs for a server",
    description="Returns all collector configurations linked to a specific server, including their active status and collection interval.",
    responses={
        404: {"model": ErrorMessage, "description": "Server not found"},
        **COMMON_RESPONSES
    }
)
async def get_server_configs(server_id: str):
    async with DatabaseConnection() as conn:
        server_repo = ServerRepository(conn)
        server = await server_repo.find_one_by(public_id=server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

        config_repo = ConfigServerRepository(conn)
        configs = await config_repo.find_by(server_id=server.id)

        return [ConfigItem.model_validate(c) for c in configs]


@router.patch(
    "/{config_id}",
    response_model=ConfigItem,
    summary="Update a collector config",
    description="Partially updates a server collector configuration. Supports changing the collection interval (in seconds) and pausing/resuming the collector.",
    responses={
        404: {"model": ErrorMessage, "description": "Server or Config not found"},
        400: {"model": ErrorMessage, "description": "No fields to update"},
        **COMMON_RESPONSES
    }
)
async def patch_server_config(server_id: str, config_id: int, patch: ConfigPatch):
    async with DatabaseConnection() as conn:
        server_repo = ServerRepository(conn)
        server = await server_repo.find_one_by(public_id=server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

        config_repo = ConfigServerRepository(conn)
        config = await config_repo.find_by_id(config_id)
        if not config or config.server_id != server.id:
            raise HTTPException(status_code=404, detail="Config not found for this server")

        updates = patch.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updated = await config_repo.update(config_id, updates)
        return ConfigItem.model_validate(updated)


@router.get(
    "/runs/stream",
    summary="SSE stream of collector runs",
    description="Server-Sent Events endpoint that streams the current status of all collector runs (server and database level) for a specific server. Updates every 2 seconds.",
    responses={
        404: {"model": ErrorMessage, "description": "Server not found"},
        **COMMON_RESPONSES
    }
)
async def stream_runs(server_id: str):
    async with DatabaseConnection() as conn:
        server_repo = ServerRepository(conn)
        server = await server_repo.find_one_by(public_id=server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

    return EventSourceResponse(run_services.run_stream(server_id))


@router.get(
    "/runs/history",
    response_model=List[RunHistoryItem],
    summary="List run execution history",
    description="Returns the execution history (collector runs) for all server-level and database-level collectors linked to a specific server.",
    responses={
        404: {"model": ErrorMessage, "description": "Server not found"},
        **COMMON_RESPONSES
    }
)
async def get_run_history(
    server_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    async with DatabaseConnection() as conn:
        server_repo = ServerRepository(conn)
        server = await server_repo.find_one_by(public_id=server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

    history = await run_services.list_run_history(server_id, limit=limit, offset=offset)
    return history


@router.patch(
    "/runs/{run_id}",
    response_model=RunControlResult,
    summary="Control a collector run",
    description="Controls a collector run by pausing, resuming, stopping or deleting it. The run type ('server' or 'database') must be provided as a query parameter.",
    responses={
        404: {"model": ErrorMessage, "description": "Server or run not found"},
        400: {"model": ErrorMessage, "description": "Invalid action or run type"},
        **COMMON_RESPONSES
    }
)
async def patch_run(
    server_id: str,
    run_id: int,
    patch: RunPatch,
    run_type: RunType = Query(..., description="Run type: 'server' or 'database'"),
):
    async with DatabaseConnection() as conn:
        server_repo = ServerRepository(conn)
        server = await server_repo.find_one_by(public_id=server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

    try:
        result = await run_services.patch_run(run_id, run_type.value, patch.action.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return RunControlResult.model_validate(result)
