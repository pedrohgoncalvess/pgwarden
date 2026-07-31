"""Pydantic models for persisted Analytics recommendations."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class AnalyticsRecommendation(BaseModel):
    """An actionable Analytics finding and the evidence that supports it."""

    id: int
    database_id: UUID
    category: str
    severity: Literal["info", "warning", "critical"]
    confidence: float
    title: str
    summary: str
    recommendation: str | None
    evidence: dict[str, Any]
    status: Literal["open", "dismissed", "resolved"]
    first_seen_at: datetime
    last_seen_at: datetime


class AnalyticsRecommendationList(BaseModel):
    """Recommendations for a single monitored database."""

    database_id: UUID
    items: list[AnalyticsRecommendation]


class AnalyticsRecommendationPatch(BaseModel):
    """A lifecycle update for one recommendation."""

    status: Literal["open", "dismissed", "resolved"]
