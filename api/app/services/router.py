from app.access.policy import access_context
"""Configuration endpoints for background services."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.auth.services import get_current_user
from database.connection import DatabaseConnection


class AnalyticsServiceConfig(BaseModel):
    """Analytics scheduling and analysis switches for one database."""

    id: int
    database_id: str
    database_name: str
    run_interval: int
    query_analytics_enabled: bool
    recommendation_enabled: bool
    last_seen: datetime | None


class AnalyticsServiceConfigPatch(BaseModel):
    """Editable Analytics service configuration values."""

    run_interval: int | None = Field(default=None, ge=10)
    query_analytics_enabled: bool | None = None
    recommendation_enabled: bool | None = None


router = APIRouter(
    prefix="/services",
    tags=["services"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/analytics/configs", response_model=list[AnalyticsServiceConfig])
async def list_analytics_configs() -> list[dict]:
    """List Analytics configurations created for monitored databases."""
    async with DatabaseConnection() as conn:
        result = await conn.execute(
            text(
                """
                SELECT config.id, database.public_id::text AS database_id,
                       database.db_name AS database_name, config.run_interval,
                       config.query_analytics_enabled, config.recommendation_enabled,
                       config.last_seen
                FROM analytics.config AS config
                JOIN metadata.database AS database ON database.id = config.database_id
                WHERE database.deleted_at IS NULL
                ORDER BY database.db_name
                """
            )
        )
        access = access_context()
        return [dict(row) for row in result.mappings() if access.admin or row["database_id"] in access.databases]


@router.patch("/analytics/configs/{config_id}", response_model=AnalyticsServiceConfig)
async def patch_analytics_config(
    config_id: int, patch: AnalyticsServiceConfigPatch
) -> dict:
    """Update Analytics scheduling or enabled analysis features."""
    fields = patch.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No configuration changes supplied")

    assignments = ", ".join(f"{field} = :{field}" for field in fields)
    async with DatabaseConnection() as conn:
        result = await conn.execute(
            text(
                f"""
                UPDATE analytics.config SET {assignments}
                WHERE id = :config_id
                RETURNING id, database_id, run_interval, query_analytics_enabled,
                          recommendation_enabled, last_seen
                """
            ),
            {"config_id": config_id, **fields},
        )
        updated = result.mappings().one_or_none()
        if updated is None:
            raise HTTPException(status_code=404, detail="Analytics configuration not found")
        database = await conn.execute(
            text(
                "SELECT public_id::text AS database_id, db_name AS database_name "
                "FROM metadata.database WHERE id = :database_id"
            ),
            {"database_id": updated["database_id"]},
        )
        database_row = database.mappings().one()
        await conn.commit()
        return {**dict(updated), **dict(database_row)}
