from typing import List

from fastapi import APIRouter, HTTPException, Depends

from app.servers.config.models import ConfigItem, ConfigPatch
from database.connection import DatabaseConnection
from database.operations.collector.config import ConfigServerRepository
from database.operations.collector.server import ServerRepository
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
