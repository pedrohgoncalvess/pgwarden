from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from analytics.services.recommendations import RecommendationDraft, _upsert


def recommendation(severity: str) -> RecommendationDraft:
    return RecommendationDraft(
        fingerprint="maintenance:public.orders",
        category="maintenance",
        severity=severity,
        confidence=0.95,
        title="Orders require immediate maintenance",
        summary="Table health has crossed a critical threshold.",
        recommendation="Schedule maintenance immediately.",
        evidence={"table": "public.orders"},
    )


@pytest.mark.asyncio
async def test_upsert_creates_notification_for_critical_recommendation() -> None:
    session = SimpleNamespace(execute=AsyncMock())

    await _upsert(session, 7, recommendation("critical"))

    assert session.execute.await_count == 2
    notification_call = session.execute.await_args_list[1]
    assert "INSERT INTO notifier.notification" in str(notification_call.args[0])
    assert notification_call.args[1]["database_id"] == 7
    assert notification_call.args[1]["fingerprint"] == "maintenance:public.orders"


@pytest.mark.asyncio
async def test_upsert_does_not_notify_noncritical_recommendation() -> None:
    session = SimpleNamespace(execute=AsyncMock())

    await _upsert(session, 7, recommendation("warning"))

    session.execute.assert_awaited_once()
