import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.notifier.notification import Notification


@pytest_asyncio.fixture
async def test_notifications(db_session: AsyncSession) -> list[Notification]:
    rows = [
        Notification(
            message="CPU is critical",
            params={"severity": "critical", "source": "alerts"},
        ),
        Notification(
            message="Query latency is elevated",
            params={"severity": "warning", "source": "analytics"},
        ),
        Notification(
            message="Collector completed",
            hidden=True,
            params={"severity": "info", "source": "collector"},
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    for row in rows:
        await db_session.refresh(row)
    return rows


@pytest.mark.asyncio
async def test_list_visible_notifications(
    auth_client: AsyncClient,
    test_notifications: list[Notification],
) -> None:
    response = await auth_client.get("/v1/notifications/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["visible_count"] == 2
    assert data["hidden_count"] == 1
    assert data["level_counts"] == {"critical": 1, "warning": 1, "info": 0}


@pytest.mark.asyncio
async def test_filter_notifications_by_level(
    auth_client: AsyncClient,
    test_notifications: list[Notification],
) -> None:
    response = await auth_client.get("/v1/notifications/?level=critical")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["message"] == "CPU is critical"


@pytest.mark.asyncio
async def test_hide_and_restore_notification(
    auth_client: AsyncClient,
    test_notifications: list[Notification],
) -> None:
    notification = test_notifications[0]

    hidden_response = await auth_client.patch(
        f"/v1/notifications/{notification.id}",
        json={"hidden": True},
    )
    assert hidden_response.status_code == 200
    assert hidden_response.json()["hidden"] is True

    restored_response = await auth_client.patch(
        f"/v1/notifications/{notification.id}",
        json={"hidden": False},
    )
    assert restored_response.status_code == 200
    assert restored_response.json()["hidden"] is False


@pytest.mark.asyncio
async def test_patch_notification_not_found(auth_client: AsyncClient) -> None:
    response = await auth_client.patch(
        "/v1/notifications/999999",
        json={"hidden": True},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_notifications_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/v1/notifications/")
    assert response.status_code == 401
