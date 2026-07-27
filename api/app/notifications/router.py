from fastapi import APIRouter, Depends, Query

from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES, ErrorMessage
from app.notifications.models import (
    NotificationLevel,
    NotificationListResponse,
    NotificationPatch,
    NotificationResponse,
)
from app.notifications.services import list_notifications, set_notification_hidden
from database.connection import DatabaseConnection


router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/",
    response_model=NotificationListResponse,
    summary="List notifications",
    description="Lists visible or hidden notifications ordered from newest to oldest.",
    responses={**COMMON_RESPONSES},
)
async def get_notifications(
    hidden: bool = Query(False, description="Return hidden notifications"),
    level: NotificationLevel | None = Query(None, description="Filter by notification level"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> NotificationListResponse:
    """List notifications for the frontend notification center."""
    async with DatabaseConnection() as conn:
        return await list_notifications(conn, hidden, level, limit, offset)


@router.patch(
    "/{notification_id}",
    response_model=NotificationResponse,
    summary="Hide or restore a notification",
    responses={
        404: {"model": ErrorMessage, "description": "Notification not found"},
        **COMMON_RESPONSES,
    },
)
async def patch_notification(
    notification_id: int,
    patch: NotificationPatch,
) -> NotificationResponse:
    """Update the hidden state of a notification."""
    async with DatabaseConnection() as conn:
        return await set_notification_hidden(conn, notification_id, patch.hidden)
