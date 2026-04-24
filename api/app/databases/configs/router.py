from typing import List

from fastapi import APIRouter, HTTPException, Depends

from app.databases.configs.models import ConfigItem, ConfigPatch
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection
from database.operations.collector.config import ConfigDatabaseRepository
from database.operations.metadata.database import DatabaseRepository
from app.auth.services import get_current_user


router = APIRouter(
    prefix="/databases/{database_id}/configs",
    tags=["databases"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/",
    response_model=List[ConfigItem],
    summary="List collector configs for a database",
    description="Returns all collector configurations linked to a specific database, including their active status and collection interval.",
    responses={
        404: {"model": ErrorMessage, "description": "Database not found"},
        **COMMON_RESPONSES
    }
)
async def get_database_configs(database_id: str):
    async with DatabaseConnection() as conn:
        db_repo = DatabaseRepository(conn)
        database = await db_repo.find_one_by(public_id=database_id)
        if not database:
            raise HTTPException(status_code=404, detail="Database not found")

        config_repo = ConfigDatabaseRepository(conn)
        configs = await config_repo.find_by(database_id=database.id)

        return [ConfigItem.model_validate(c) for c in configs]


@router.patch(
    "/{config_id}",
    response_model=ConfigItem,
    summary="Update a collector config",
    description="Partially updates a collector configuration. Supports changing the collection interval (in seconds) and pausing/resuming the collector.",
    responses={
        404: {"model": ErrorMessage, "description": "Database or Config not found"},
        400: {"model": ErrorMessage, "description": "No fields to update"},
        **COMMON_RESPONSES
    }
)
async def patch_database_config(database_id: str, config_id: int, patch: ConfigPatch):
    async with DatabaseConnection() as conn:
        db_repo = DatabaseRepository(conn)
        database = await db_repo.find_one_by(public_id=database_id)
        if not database:
            raise HTTPException(status_code=404, detail="Database not found")

        config_repo = ConfigDatabaseRepository(conn)
        config = await config_repo.find_by_id(config_id)
        if not config or config.database_id != database.id:
            raise HTTPException(status_code=404, detail="Config not found for this database")

        updates = patch.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updated = await config_repo.update(config_id, updates)
        return ConfigItem.model_validate(updated)
