"""Bounded HTTP ingestion with project credentials and transactional delivery."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy.exc import DataError, IntegrityError

from app.ingestion.auth import authenticate_key
from app.ingestion.models import EventBatch, IngestionResult, get_batch_schema
from app.ingestion.services import receive_events
from database.connection import DatabaseConnection


router = APIRouter(prefix="/ingestion", tags=["ingestion"])
security = HTTPBearer(auto_error=False)
MAX_BATCH_BYTES = 2 * 1024 * 1024


async def read_batch(request: Request) -> EventBatch:
    """Bound the streamed body before decoding JSON or allocating event models."""
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BATCH_BYTES:
            raise HTTPException(413, "Event batch exceeds 2 MiB")
    try:
        return EventBatch.model_validate_json(bytes(body))
    except ValidationError:
        raise HTTPException(
            422, "Invalid event batch; use version 1 and between 1 and 500 events"
        ) from None


@router.post(
    "/events",
    response_model=IngestionResult,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": get_batch_schema()}},
        },
    },
)
async def ingest_events(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Receive SQLite snapshots; the bearer key selects the project implicitly."""
    response.headers["Cache-Control"] = "no-store"
    if credentials is None:
        raise HTTPException(
            401, "Ingestion key required", headers={"WWW-Authenticate": "Bearer"}
        )
    batch = await read_batch(request)
    async with DatabaseConnection() as session:
        try:
            settings, key = await authenticate_key(session, credentials.credentials)
            return await receive_events(session, settings, key, batch)
        except (IntegrityError, DataError):
            await session.rollback()
            raise HTTPException(
                422, "Event rows violate destination constraints"
            ) from None
        except BaseException:
            await session.rollback()
            raise
