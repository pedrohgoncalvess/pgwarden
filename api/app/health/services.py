"""Service heartbeat health checks."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.health.models import HealthResponse, ServiceHealth


SERVICE_TIMEOUTS = {"collector": 90, "analytics": 90, "notifier": 90}


async def get_health(session: AsyncSession) -> HealthResponse:
    """Return whether each background service has reported recently."""
    result = await session.execute(
        text("SELECT service, updated_at FROM base.service_heartbeat")
    )
    updated_at = {row.service: row.updated_at for row in result.mappings()}
    now = datetime.now(timezone.utc)
    services = {
        service: ServiceHealth(
            status=(
                "healthy"
                if updated_at.get(service)
                and now - updated_at[service] <= timedelta(seconds=timeout)
                else "unavailable"
            ),
            updated_at=updated_at.get(service),
        )
        for service, timeout in SERVICE_TIMEOUTS.items()
    }
    status = "healthy" if all(item.status == "healthy" for item in services.values()) else "unavailable"
    return HealthResponse(status=status, services=services)
