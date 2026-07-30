"""Schemas returned by the service health API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


ServiceStatus = Literal["healthy", "unavailable"]


class ServiceHealth(BaseModel):
    """Current heartbeat status for one background service."""

    status: ServiceStatus
    updated_at: datetime | None


class HealthResponse(BaseModel):
    """Availability status for PGWarden background services."""

    status: ServiceStatus
    services: dict[str, ServiceHealth]
