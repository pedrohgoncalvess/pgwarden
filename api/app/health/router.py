"""Service health endpoint."""

from fastapi import APIRouter

from app.health.models import HealthResponse
from app.health.services import get_health
from database.connection import DatabaseConnection


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Check background services")
async def health() -> HealthResponse:
    """Return collector, analytics, and notifier heartbeat status."""
    async with DatabaseConnection() as session:
        return await get_health(session)
