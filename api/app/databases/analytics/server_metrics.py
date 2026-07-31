"""Historical server metrics used by the Deep analytics workspace."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.schemas.exceptions import DatabaseNotFoundError
from database.models.metadata.database import Database
from database.models.metric.cpu import CpuMetric
from database.models.metric.disk import DiskMetric
from database.models.metric.io import IoMetric
from database.models.metric.ram import RamMetric


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse a client-supplied ISO datetime as UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _date_range(start_date: Optional[str], end_date: Optional[str]) -> tuple[datetime, datetime]:
    """Return a safe default range when a client does not supply one."""
    end_at = _parse_date(end_date) or datetime.now(timezone.utc)
    return _parse_date(start_date) or end_at - timedelta(days=7), end_at


async def get_server_metrics(
    db: AsyncSession,
    database_id: UUID,
    start_date: Optional[str],
    end_date: Optional[str],
) -> dict:
    """Return CPU, memory, disk and I/O snapshots for a database's server."""
    database = (
        await db.execute(
            select(Database).where(
                Database.public_id == database_id, Database.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if not database:
        raise DatabaseNotFoundError(str(database_id))

    start_at, end_at = _date_range(start_date, end_date)
    filters = lambda model: and_(
        model.server_id == database.server_id,
        model.collected_at >= start_at,
        model.collected_at <= end_at,
    )
    cpu_rows = (
        await db.execute(
            select(CpuMetric.collected_at, CpuMetric.cpu_percent).where(filters(CpuMetric))
        )
    ).all()
    ram_rows = (
        await db.execute(
            select(RamMetric.collected_at, RamMetric.percent).where(filters(RamMetric))
        )
    ).all()
    io_rows = (
        await db.execute(
            select(IoMetric.collected_at, IoMetric.read_bytes, IoMetric.write_bytes).where(filters(IoMetric))
        )
    ).all()
    disk_rows = (
        await db.execute(
            select(DiskMetric.collected_at, DiskMetric.percent).where(filters(DiskMetric))
        )
    ).all()

    points: dict[datetime, dict] = defaultdict(dict)
    for collected_at, percent in cpu_rows:
        points[collected_at]["cpu_percent"] = percent
    for collected_at, percent in ram_rows:
        points[collected_at]["ram_percent"] = percent
    for collected_at, read_bytes, write_bytes in io_rows:
        points[collected_at].update(read_bytes=read_bytes, write_bytes=write_bytes)
    disk_values: dict[datetime, list[float]] = defaultdict(list)
    for collected_at, percent in disk_rows:
        if percent is not None:
            disk_values[collected_at].append(percent)
    for collected_at, values in disk_values.items():
        points[collected_at]["disk_percent"] = round(sum(values) / len(values), 2)

    items = [{"collected_at": time, **values} for time, values in sorted(points.items())]
    return {"database_id": database_id, "start_at": start_at, "end_at": end_at, "items": items}
