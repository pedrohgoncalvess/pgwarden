from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from analytics.services.runs import (
    _effective_interval,
    _record_run_error,
    prepare_due_analytics_with_session,
)


def test_effective_interval_uses_default_and_minimum() -> None:
    assert _effective_interval(None) == 1800
    assert _effective_interval(1) == 10
    assert _effective_interval(120) == 120


@pytest.mark.asyncio
async def test_prepare_due_run_marks_execution_and_queues_next() -> None:
    run = SimpleNamespace(id=4, database_id=7, status="scheduled", started_at=None)
    config = SimpleNamespace(
        id=2,
        run_interval=60,
        query_analytics_enabled=True,
        recommendation_enabled=True,
    )
    session = SimpleNamespace(add=lambda item: added.append(item), commit=AsyncMock())
    added = []

    with patch("analytics.services.runs._due_runs", new=AsyncMock(return_value=[(run, config)])):
        requests = await prepare_due_analytics_with_session(session, set())

    assert run.status == "running"
    assert run.started_at is not None
    assert len(added) == 1
    assert added[0].database_id == 7
    assert added[0].run_at > run.started_at
    assert requests[0].run_id == 4
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_run_error_completes_failed_execution() -> None:
    run = SimpleNamespace(error=None, status="running", finished_at=None)
    session = SimpleNamespace(get=AsyncMock(return_value=run), commit=AsyncMock())

    await _record_run_error(session, 4, "database unavailable")

    assert run.error == "database unavailable"
    assert run.status == "error"
    assert run.finished_at is not None
    session.commit.assert_awaited_once()
