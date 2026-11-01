"""Check retention estimates, validation, catalog guards and job updates."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.retention.estimates import estimate_storage
from app.retention.models import RetentionWindow
from app.retention import services
from app.retention.router import router
from app.projects.router import require_admin
from app.auth.services import get_current_user


NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def chunk(
    start_days: int, end_days: int, size: int = 1000, compressed: bool = False
) -> dict[str, Any]:
    return {"range_start": NOW - timedelta(days=start_days),
            "range_end": NOW - timedelta(days=end_days),
            "total_bytes": size, "is_compressed": compressed}


def test_increasing_and_decreasing_storage() -> None:
    chunks = [chunk(10, 5, compressed=True), chunk(5, 0)]
    for target, expected, delta in [(20, 4000, 2000), (5, 1000, -1000)]:
        result = estimate_storage(chunks, NOW - timedelta(days=10), NOW,
                                  NOW, NOW - timedelta(days=target),
                                  target * 86400, 10 * 86400)
        assert result["projected_bytes"] == expected
        assert result["policy_delta_bytes"] == delta
        assert result["bytes_per_day"] == 200
        assert result["compressed_chunks"] == 1


def test_only_whole_expired_chunks_are_reclaimable() -> None:
    result = estimate_storage([chunk(10, 5), chunk(5, 0)],
                              NOW - timedelta(days=10), NOW, NOW,
                              NOW - timedelta(days=3), 3 * 86400, None)
    assert result["eligible_chunks"] == 1
    assert result["reclaimable_bytes"] == 1000
    assert result["policy_delta_bytes"] is None
    assert result["footprint_delta_bytes"] == -1400


@pytest.mark.parametrize("first,last", [(None, None), (NOW, NOW),
    (NOW - timedelta(seconds=30), NOW)])
def test_no_growth_invented_for_insufficient_history(
    first: datetime | None, last: datetime | None
) -> None:
    result = estimate_storage([], first, last, NOW, NOW, 60, 60)
    assert result["projected_bytes"] is None
    assert result["confidence"] == "insufficient_data"
    assert result["reclaimable_bytes"] == 0


def test_inactive_collection_uses_time_until_now() -> None:
    result = estimate_storage([chunk(10, 0)], NOW - timedelta(days=10),
                              NOW - timedelta(days=9), NOW, NOW, 86400, 86400)
    assert result["bytes_per_day"] == 100


@pytest.mark.parametrize("body", [
    {"value": 0, "unit": "days"}, {"value": -1, "unit": "days"},
    {"value": 1.5, "unit": "days"}, {"value": 100001, "unit": "days"},
    {"value": 1, "unit": "years"}, {"value": 1, "unit": "days; DROP TABLE metric.cpu"},
])
def test_invalid_windows_are_rejected(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RetentionWindow(**body)


@pytest.mark.parametrize("unit", ["minutes", "hours", "days", "weeks", "months"])
def test_all_requested_units_are_supported(unit: str) -> None:
    assert RetentionWindow(value=2, unit=unit).unit == unit


async def test_unknown_table_is_rejected_before_identifier_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    monkeypatch.setattr(services, "list_policies", AsyncMock(return_value=[]))
    with pytest.raises(HTTPException) as error:
        await services.preview_policy(session, 'cpu"; DROP SCHEMA metric',
                                      RetentionWindow(value=1, unit="days"))
    assert error.value.status_code == 404
    session.execute.assert_not_called()


async def test_existing_job_preserves_other_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    policy = {"name": "cpu", "job_id": 42}
    monkeypatch.setattr(services, "get_policy", AsyncMock(return_value=policy))
    await services.update_policy(session, "cpu", RetentionWindow(value=2, unit="months"))
    statement, parameters = session.execute.call_args_list[1].args
    assert "alter_job" in str(statement)
    assert "config - 'drop_created_before'" in str(statement)
    assert "scheduled =>" not in str(statement)
    assert "remove_retention_policy" not in str(statement)
    assert parameters == {"interval": "2 months", "job_id": 42}
    session.commit.assert_awaited_once()


async def test_missing_job_is_created(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    monkeypatch.setattr(services, "get_policy", AsyncMock(
        return_value={"name": "native_query", "job_id": None}))
    await services.update_policy(session, "native_query", RetentionWindow(value=15, unit="minutes"))
    statement, parameters = session.execute.call_args_list[1].args
    assert "add_retention_policy" in str(statement)
    assert parameters == {"interval": "15 minutes", "relation": '"metric"."native_query"'}
    session.commit.assert_awaited_once()


async def test_all_routes_require_an_administrator() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(is_admin=False)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        for method, path in [("GET", "/retention"), ("POST", "/retention/cpu/preview"),
                             ("PUT", "/retention/cpu")]:
            response = await client.request(method, path, json={"value": 1, "unit": "days"})
            assert response.status_code == 403


async def test_admin_dependency_accepts_administrator() -> None:
    user = SimpleNamespace(is_admin=True)
    assert await require_admin(user) is user
