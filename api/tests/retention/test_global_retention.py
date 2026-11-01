"""Verify atomic global replication and complete consolidated estimates."""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, call

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.auth.services import get_current_user
from app.retention import global_policies, services
from app.retention.models import RetentionWindow
from app.retention.router import router


WINDOW = RetentionWindow(value=3, unit="months")
TARGETS = [{"name": "ram", "job_id": None}, {"name": "cpu", "job_id": 1}]


def make_preview(name: str) -> dict[str, Any]:
    """Provide one table's independently calculated preview."""
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    return {"name": name, "measured_at": now, "cutoff": now,
            "first_sample": now, "last_sample": now, "observed_seconds": 60,
            "confidence": "limited", **{key: 100 for key in (
                "current_bytes", "bytes_per_day", "projected_bytes",
                "baseline_projected_bytes", "policy_delta_bytes", "footprint_delta_bytes",
                "reclaimable_bytes", "eligible_chunks", "total_chunks", "compressed_chunks",
            )}}


async def test_global_save_commits_once_in_stable_lock_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Include unconfigured tables and commit only after all updates succeed."""
    session = AsyncMock()
    monkeypatch.setattr(services, "list_policies", AsyncMock(return_value=TARGETS))
    apply = AsyncMock()
    monkeypatch.setattr(services, "apply_policy", apply)
    assert await global_policies.update_global(session, WINDOW) == TARGETS
    assert apply.await_args_list == [call(session, "cpu", WINDOW), call(session, "ram", WINDOW)]
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


async def test_global_failure_rolls_back_without_partial_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Roll back earlier updates when a later policy fails."""
    session = AsyncMock()
    monkeypatch.setattr(services, "list_policies", AsyncMock(return_value=TARGETS))
    monkeypatch.setattr(services, "apply_policy", AsyncMock(side_effect=[None, RuntimeError("failed")]))
    with pytest.raises(RuntimeError, match="failed"):
        await global_policies.update_global(session, WINDOW)
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


async def test_global_preview_sums_independent_table_estimates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aggregate projections while retaining individual previews."""
    monkeypatch.setattr(services, "list_policies", AsyncMock(return_value=TARGETS))
    monkeypatch.setattr(services, "preview_policy", AsyncMock(side_effect=[make_preview("cpu"), make_preview("ram")]))
    result = await global_policies.preview_global(AsyncMock(), WINDOW)
    assert result["name"] == "__all__"
    assert result["current_bytes"] == 200
    assert result["projected_bytes"] == 200
    assert [table["name"] for table in result["tables"]] == ["cpu", "ram"]


async def test_missing_history_does_not_produce_a_partial_global_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expose physical totals but leave incomplete projections unknown."""
    missing = {**make_preview("ram"), "projected_bytes": None,
               "baseline_projected_bytes": None, "policy_delta_bytes": None,
               "confidence": "insufficient_data"}
    monkeypatch.setattr(services, "list_policies", AsyncMock(return_value=TARGETS))
    monkeypatch.setattr(services, "preview_policy", AsyncMock(side_effect=[make_preview("cpu"), missing]))
    result = await global_policies.preview_global(AsyncMock(), WINDOW)
    assert result["projected_bytes"] is None
    assert result["baseline_projected_bytes"] is None
    assert result["policy_delta_bytes"] is None
    assert result["reclaimable_bytes"] == 200
    assert result["confidence"] == "insufficient_data"


async def test_no_targets_cannot_report_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject global saves with no available metric hypertables."""
    session = AsyncMock()
    monkeypatch.setattr(services, "list_policies", AsyncMock(return_value=[]))
    with pytest.raises(HTTPException) as error:
        await global_policies.update_global(session, WINDOW)
    assert error.value.status_code == 404
    session.commit.assert_not_awaited()


async def test_global_endpoints_require_admin() -> None:
    """Protect global operations with the same administrator requirement."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(is_admin=False)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        for method, path in [("POST", "/retention/global/preview"), ("PUT", "/retention/global")]:
            response = await client.request(method, path, json=WINDOW.model_dump())
            assert response.status_code == 403
