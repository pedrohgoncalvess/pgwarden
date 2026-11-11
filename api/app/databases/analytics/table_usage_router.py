"""HTTP endpoints for parsed query usage by schema table."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.services import get_current_user
from app.databases.analytics.table_usage import (
    get_column_usage,
    get_table_usage,
    get_table_usage_available,
)
from database.connection import DatabaseConnection


class TableUsageAvailabilityResponse(BaseModel):
    """Whether Analytics has parsed query data for the database."""

    available: bool


class TableQueryUsageItem(BaseModel):
    """Captured workload information for one parsed query."""

    sources: list[str] = []
    pg_query_id: str | None = None
    activity_executions: int = 0
    statements_calls: int | None = None
    metrics_source: str = "activity"
    query: str
    execution_count: int
    last_executed_at: datetime | None
    avg_duration_ms: float | None


class TableUsageResponse(BaseModel):
    """Parsed queries that use one tracked schema table."""

    items: list[TableQueryUsageItem]


class ColumnQueryUsageItem(TableQueryUsageItem):
    """Captured workload information for one parsed column reference."""

    is_selected: bool
    is_condition: bool
    is_condition_foreign: bool


class ColumnUsageResponse(BaseModel):
    """Parsed queries that use one tracked schema column."""

    items: list[ColumnQueryUsageItem]


router = APIRouter(
    prefix="/databases/{database_id}/analytics/table-usage",
    tags=["analytics"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/{table_id}/availability", response_model=TableUsageAvailabilityResponse)
async def get_usage_availability(
    database_id: UUID, table_id: UUID
) -> TableUsageAvailabilityResponse:
    """Check whether table usage can be shown."""
    async with DatabaseConnection() as conn:
        return TableUsageAvailabilityResponse(
            available=await get_table_usage_available(conn, database_id, table_id)
        )


@router.get("/{table_id}", response_model=TableUsageResponse)
async def get_usage(database_id: UUID, table_id: UUID) -> TableUsageResponse:
    """Get parsed queries and their captured workload for a table."""
    async with DatabaseConnection() as conn:
        return TableUsageResponse(items=await get_table_usage(conn, database_id, table_id))


@router.get(
    "/{table_id}/columns/{column_id}",
    response_model=ColumnUsageResponse,
)
async def get_column_query_usage(
    database_id: UUID,
    table_id: UUID,
    column_id: UUID,
) -> ColumnUsageResponse:
    """Get parsed queries and their captured workload for a column."""
    async with DatabaseConnection() as conn:
        return ColumnUsageResponse(
            items=await get_column_usage(conn, database_id, table_id, column_id)
        )
