import asyncio
import json
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, desc

from database.connection import DatabaseConnection
from database.models.collector.server import Server
from database.models.collector.command import Command
from database.models.collector.config_server import ConfigServer
from database.models.collector.config_database import ConfigDatabase
from database.models.collector.run import Run
from database.models.metadata.database import Database


def _serialize_run_snapshot(item: dict) -> dict:
    """Serialize a run snapshot for SSE payloads."""
    next_run = item.get("next_run_at")
    if isinstance(next_run, datetime):
        next_run = next_run.isoformat()
    return {
        "id": item["id"],
        "server_id": item["server_id"],
        "database_id": item.get("database_id"),
        "database_name": item.get("database_name"),
        "name": item["name"],
        "type": item["type"],
        "interval": item["interval"],
        "is_paused": item["is_paused"],
        "next_run_at": next_run,
        "status": item["status"],
    }


def _derive_status(is_paused: bool, next_run_at: Optional[datetime]) -> str:
    if is_paused:
        return "paused"
    if next_run_at is None:
        return "idle"
    if next_run_at <= datetime.now(timezone.utc):
        return "running"
    return "idle"


def _serialize_run(row: Run, config_lookup: dict) -> dict:
    config_id = row.config_server_id or row.config_database_id
    lookup_key = ("server", row.config_server_id) if row.config_server_id else ("database", row.config_database_id)
    meta = config_lookup.get(lookup_key) or config_lookup.get(config_id, {})
    finished = row.finished_at.isoformat() if row.finished_at else None
    inserted = row.inserted_at.isoformat() if row.inserted_at else None
    return {
        "id": row.id,
        "config_id": config_id,
        "database_id": meta.get("database_id"),
        "database_name": meta.get("database_name"),
        "name": meta.get("name"),
        "type": meta.get("type"),
        "status": row.status,
        "errors": row.errors or [],
        "started_at": inserted,
        "finished_at": finished,
    }


async def _get_server_internal_id(server_id: str) -> Optional[int]:
    async with DatabaseConnection() as conn:
        result = await conn.execute(
            select(Server.id).where(Server.public_id == server_id)
        )
        return result.scalar_one_or_none()


async def _get_database_internal_id(database_id: str) -> Optional[int]:
    async with DatabaseConnection() as conn:
        result = await conn.execute(
            select(Database.id).where(Database.public_id == database_id)
        )
        return result.scalar_one_or_none()


async def _get_runs_by_server(server_id: str):
    internal_id = await _get_server_internal_id(server_id)
    if internal_id is None:
        return None

    async with DatabaseConnection() as conn:
        srv_result = await conn.execute(
            select(ConfigServer).where(ConfigServer.server_id == internal_id)
        )
        server_configs = srv_result.scalars().all()

    runs = []
    for cfg in server_configs:
        runs.append({
            "id": cfg.id,
            "server_id": cfg.server_id,
            "database_id": None,
            "database_name": None,
            "name": cfg.name,
            "type": "server",
            "interval": cfg.interval,
            "is_paused": cfg.is_paused,
            "next_run_at": cfg.next_run_at,
            "status": _derive_status(cfg.is_paused, cfg.next_run_at),
        })

    return runs


async def _get_runs_by_database(database_id: str):
    internal_id = await _get_database_internal_id(database_id)
    if internal_id is None:
        return None

    async with DatabaseConnection() as conn:
        db_result = await conn.execute(
            select(Database.server_id, Database.db_name).where(Database.id == internal_id)
        )
        row = db_result.one_or_none()
        if row is None:
            return None
        server_id, db_name = row

        db_cfg_result = await conn.execute(
            select(ConfigDatabase).where(ConfigDatabase.database_id == internal_id)
        )
        db_configs = db_cfg_result.scalars().all()

    runs = []
    for cfg in db_configs:
        runs.append({
            "id": cfg.id,
            "server_id": server_id,
            "database_id": internal_id,
            "database_name": db_name,
            "name": cfg.name,
            "type": "database",
            "interval": cfg.interval,
            "is_paused": cfg.is_paused,
            "next_run_at": cfg.next_run_at,
            "status": _derive_status(cfg.is_paused, cfg.next_run_at),
        })

    return runs


async def run_stream(server_id: str):
    while True:
        try:
            runs = await _get_runs_by_server(server_id)
            if runs is None:
                yield {"event": "error", "data": json.dumps({"error": "Server not found"})}
                await asyncio.sleep(2)
                continue

            payload = [_serialize_run_snapshot(r) for r in runs]
            yield {"event": "runs", "data": json.dumps(payload)}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

        await asyncio.sleep(2)


async def database_run_stream(database_id: str):
    while True:
        try:
            runs = await _get_runs_by_database(database_id)
            if runs is None:
                yield {"event": "error", "data": json.dumps({"error": "Database not found"})}
                await asyncio.sleep(2)
                continue

            payload = [_serialize_run_snapshot(r) for r in runs]
            yield {"event": "runs", "data": json.dumps(payload)}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

        await asyncio.sleep(2)


async def list_run_history(server_id: str, limit: int = 100, offset: int = 0) -> List[dict]:
    internal_id = await _get_server_internal_id(server_id)
    if internal_id is None:
        return []

    async with DatabaseConnection() as conn:
        srv_result = await conn.execute(
            select(ConfigServer.id, ConfigServer.name).where(ConfigServer.server_id == internal_id)
        )
        server_config_rows = srv_result.all()
        server_config_ids = [row[0] for row in server_config_rows]

        if not server_config_ids:
            return []

        config_lookup = {
            cid: {"type": "server", "name": name, "database_id": None, "database_name": None}
            for cid, name in server_config_rows
        }

        runs_result = await conn.execute(
            select(Run)
            .where(Run.config_server_id.in_(server_config_ids))
            .order_by(desc(Run.inserted_at))
            .offset(offset)
            .limit(limit)
        )
        runs = runs_result.scalars().all()

        return [_serialize_run(r, config_lookup) for r in runs]


async def list_database_run_history(database_id: str, limit: int = 100, offset: int = 0) -> List[dict]:
    internal_id = await _get_database_internal_id(database_id)
    if internal_id is None:
        return []

    async with DatabaseConnection() as conn:
        db_cfg_result = await conn.execute(
            select(ConfigDatabase.id, ConfigDatabase.database_id, ConfigDatabase.name)
            .where(ConfigDatabase.database_id == internal_id)
        )
        db_config_rows = db_cfg_result.all()
        db_config_ids = [row[0] for row in db_config_rows]

        if not db_config_ids:
            return []

        db_name_result = await conn.execute(
            select(Database.db_name).where(Database.id == internal_id)
        )
        db_name = db_name_result.scalar_one_or_none()

        config_lookup = {
            cfg_id: {
                "type": "database",
                "name": name,
                "database_id": db_id,
                "database_name": db_name,
            }
            for cfg_id, db_id, name in db_config_rows
        }

        runs_result = await conn.execute(
            select(Run)
            .where(Run.config_database_id.in_(db_config_ids))
            .order_by(desc(Run.inserted_at))
            .offset(offset)
            .limit(limit)
        )
        runs = runs_result.scalars().all()

        return [_serialize_run(r, config_lookup) for r in runs]


async def patch_run(run_id: int, run_type: str, action: str) -> dict:
    async with DatabaseConnection() as conn:
        server_id: Optional[int] = None
        if run_type == "server":
            result = await conn.execute(select(ConfigServer).where(ConfigServer.id == run_id))
            config = result.scalar_one_or_none()
            if config:
                server_id = config.server_id
        elif run_type == "database":
            result = await conn.execute(
                select(ConfigDatabase, Database.server_id)
                .join(Database, ConfigDatabase.database_id == Database.id)
                .where(ConfigDatabase.id == run_id)
            )
            row = result.one_or_none()
            config = row[0] if row else None
            server_id = row[1] if row else None
        else:
            raise ValueError("Invalid run type. Use 'server' or 'database'.")

        if not config:
            raise ValueError("Run not found")

        snapshot = {
            "id": config.id,
            "server_id": server_id,
            "database_id": getattr(config, "database_id", None),
            "name": config.name,
            "type": run_type,
            "interval": config.interval,
            "is_paused": config.is_paused,
            "next_run_at": config.next_run_at.isoformat() if config.next_run_at else None,
            "status": "deleted" if action == "delete" else _derive_status(config.is_paused, config.next_run_at),
            "action": action,
        }

        if action in ("pause", "stop"):
            config.is_paused = True
        elif action == "resume":
            config.is_paused = False
        elif action == "force_run":
            if config.is_paused:
                raise ValueError("Cannot force run a paused collector")
            command = Command(
                collector=config.name,
                command="force_run",
                payload=None,
            )
            conn.add(command)
        elif action == "delete":
            await conn.delete(config)
            await conn.commit()
            return snapshot
        else:
            raise ValueError("Invalid action. Use 'pause', 'resume', 'stop', 'delete' or 'force_run'.")

        await conn.commit()
        await conn.refresh(config)

        snapshot["is_paused"] = config.is_paused
        snapshot["next_run_at"] = config.next_run_at.isoformat() if config.next_run_at else None
        snapshot["status"] = _derive_status(config.is_paused, config.next_run_at)
        return snapshot
