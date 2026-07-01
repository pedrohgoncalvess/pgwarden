from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class QueryAnalyticsUserBreakdown(BaseModel):
    user_name: Optional[str]
    execution_count: int

    model_config = ConfigDict(from_attributes=True)


class QueryAnalyticsApplicationBreakdown(BaseModel):
    application_name: Optional[str]
    execution_count: int

    model_config = ConfigDict(from_attributes=True)


class QueryAnalyticsItem(BaseModel):
    query_signature: str
    query_preview: str
    query_hash: Optional[str]
    execution_count: int
    avg_duration_ms: Optional[float]
    max_duration_ms: Optional[float]
    min_duration_ms: Optional[float]
    total_duration_ms: Optional[float]
    unique_users: int
    user_breakdown: List[QueryAnalyticsUserBreakdown]
    unique_applications: int
    application_breakdown: List[QueryAnalyticsApplicationBreakdown]
    first_seen: datetime
    last_seen: datetime

    model_config = ConfigDict(from_attributes=True)


class QueryAnalyticsTimelinePoint(BaseModel):
    timestamp: datetime
    execution_count: int
    avg_duration_ms: Optional[float]

    model_config = ConfigDict(from_attributes=True)


class QueryAnalyticsFilters(BaseModel):
    users: List[Optional[str]]
    applications: List[Optional[str]]
    states: List[Optional[str]]

    model_config = ConfigDict(from_attributes=True)


class QueryAnalyticsResponse(BaseModel):
    database_id: UUID
    database_name: str
    start_at: datetime
    end_at: datetime
    items: List[QueryAnalyticsItem]
    total: int
    timeline: List[QueryAnalyticsTimelinePoint]
    filters: QueryAnalyticsFilters

    model_config = ConfigDict(from_attributes=True)
