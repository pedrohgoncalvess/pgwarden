"""HTTP endpoint for historical server metrics in Deep."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth.services import get_current_user
from app.databases.analytics.server_metrics import get_server_metrics
from database.connection import DatabaseConnection


class ServerMetricPoint(BaseModel):
    """One collected host-metric sample."""

    collected_at: datetime
    cpu_percent: float | None = None
    ram_percent: float | None = None
    disk_percent: float | None = None
    read_bytes: int | None = None
    write_bytes: int | None = None


class ServerMetricsHistoryResponse(BaseModel):
    """Historical host metrics for the server attached to a database."""

    database_id: UUID
    start_at: datetime
    end_at: datetime
    items: list[ServerMetricPoint]


router = APIRouter(
    prefix="/databases/{database_id}/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/server-metrics", response_model=ServerMetricsHistoryResponse)
async def get_server_metrics_history(
    database_id: UUID,
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
) -> dict:
    """Get time-series CPU, memory, disk and I/O metrics for Deep."""
    async with DatabaseConnection() as conn:
        return await get_server_metrics(conn, database_id, start_date, end_date)
