from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


NotificationLevel = Literal["critical", "warning", "info"]


class NotificationResponse(BaseModel):
    """Notification returned to the frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    message: str
    hidden: bool
    params: dict[str, Any]
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Paginated notification list with status and level counts."""

    items: list[NotificationResponse]
    total: int
    visible_count: int
    hidden_count: int
    level_counts: dict[str, int]


class NotificationPatch(BaseModel):
    """Visibility change for one notification."""

    hidden: bool
