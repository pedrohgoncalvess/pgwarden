import asyncio
import json
from datetime import datetime

from sqlalchemy import select, desc

from database.connection import DatabaseConnection
from database.models.metric.cpu import CpuMetric
from database.models.metric.ram import RamMetric
from database.models.metric.disk import DiskMetric
from database.models.metric.io import IoMetric


def serialize_row(row) -> dict:
    data = {}
    for key, value in row.__dict__.items():
        if key.startswith("_"):
            continue
        if isinstance(value, datetime):
            data[key] = value.isoformat()
        else:
            data[key] = value
    return data


async def _fetch_latest(conn, model, server_id: int, last_ts):
    result = await conn.execute(
        select(model)
        .where(model.server_id == server_id)
        .order_by(desc(model.collected_at))
        .limit(1)
    )
    latest = result.scalar_one_or_none()

    if not latest:
        return None, last_ts

    if last_ts and latest.collected_at <= last_ts:
        return None, last_ts

    new_ts = latest.collected_at

    if hasattr(model, "mount_point"):
        rows_result = await conn.execute(
            select(model)
            .where(model.server_id == server_id, model.collected_at == new_ts)
        )
        rows = rows_result.scalars().all()
        return [serialize_row(r) for r in rows], new_ts

    return serialize_row(latest), new_ts


async def server_metrics_stream(server_id: int):
    last_cpu_ts = None
    last_ram_ts = None
    last_disk_ts = None
    last_io_ts = None

    while True:
        try:
            async with DatabaseConnection() as conn:
                cpu_data, last_cpu_ts = await _fetch_latest(conn, CpuMetric, server_id, last_cpu_ts)
                ram_data, last_ram_ts = await _fetch_latest(conn, RamMetric, server_id, last_ram_ts)
                disk_data, last_disk_ts = await _fetch_latest(conn, DiskMetric, server_id, last_disk_ts)
                io_data, last_io_ts = await _fetch_latest(conn, IoMetric, server_id, last_io_ts)

            if cpu_data is not None:
                yield {"event": "cpu", "data": json.dumps(cpu_data)}

            if ram_data is not None:
                yield {"event": "ram", "data": json.dumps(ram_data)}

            if disk_data is not None:
                yield {"event": "disk", "data": json.dumps(disk_data)}

            if io_data is not None:
                yield {"event": "io", "data": json.dumps(io_data)}

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

        await asyncio.sleep(2)
