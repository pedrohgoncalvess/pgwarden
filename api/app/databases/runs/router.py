from typing import List

from fastapi import APIRouter, HTTPException, Depends, Query
from sse_starlette.sse import EventSourceResponse

from app.servers.runs.models import (
    RunPatch, RunHistoryItem, RunControlResult
)
from app.servers.runs import services as run_services
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection
from database.operations.metadata import DatabaseRepository
from app.auth.services import get_current_user


router = APIRouter(
    prefix="/databases/{database_id}/runs",
    tags=["databases"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/stream",
    summary="SSE stream of collector runs for a database",
    description="Server-Sent Events endpoint that streams the current status of all collector runs for a specific database. Updates every 2 seconds.",
    responses={
        404: {"model": ErrorMessage, "description": "Database not found"},
        **COMMON_RESPONSES
    }
)
async def stream_database_runs(database_id: str):
    async with DatabaseConnection() as conn:
        db_repo = DatabaseRepository(conn)
        database = await db_repo.find_one_by(public_id=database_id)
        if not database:
            raise HTTPException(status_code=404, detail="Database not found")

    return EventSourceResponse(run_services.database_run_stream(database_id))


@router.get(
    "/history",
    response_model=List[RunHistoryItem],
    summary="List run execution history for a database",
    description="Returns the execution history (collector runs) for all collectors linked to a specific database.",
    responses={
        404: {"model": ErrorMessage, "description": "Database not found"},
        **COMMON_RESPONSES
    }
)
async def get_database_run_history(
    database_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    run_type: str | None = Query(default=None, pattern="^(server|database)$"),
    status: str | None = Query(default=None, min_length=1),
    name: str | None = Query(default=None, min_length=1),
    started_from: str | None = Query(default=None),
    started_to: str | None = Query(default=None),
    min_duration_seconds: float | None = Query(default=None, ge=0),
    max_duration_seconds: float | None = Query(default=None, ge=0),
):
    async with DatabaseConnection() as conn:
        db_repo = DatabaseRepository(conn)
        database = await db_repo.find_one_by(public_id=database_id)
        if not database:
            raise HTTPException(status_code=404, detail="Database not found")

    history = await run_services.list_database_run_history(
        database_id,
        limit=limit,
        offset=offset,
        run_type=run_type,
        status=status,
        name=name,
        started_from=started_from,
        started_to=started_to,
        min_duration_seconds=min_duration_seconds,
        max_duration_seconds=max_duration_seconds,
    )
    return history


@router.patch(
    "/{run_id}",
    response_model=RunControlResult,
    summary="Control a collector run for a database",
    description="Controls a database-level collector run by pausing, resuming, stopping or deleting it.",
    responses={
        404: {"model": ErrorMessage, "description": "Database or run not found"},
        400: {"model": ErrorMessage, "description": "Invalid action or run type"},
        **COMMON_RESPONSES
    }
)
async def patch_database_run(
    database_id: str,
    run_id: int,
    patch: RunPatch,
):
    async with DatabaseConnection() as conn:
        db_repo = DatabaseRepository(conn)
        database = await db_repo.find_one_by(public_id=database_id)
        if not database:
            raise HTTPException(status_code=404, detail="Database not found")

    try:
        result = await run_services.patch_run(run_id, "database", patch.action.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return RunControlResult.model_validate(result)
