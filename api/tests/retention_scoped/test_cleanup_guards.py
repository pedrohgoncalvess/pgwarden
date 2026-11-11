"""Exercise cleanup refusal and calendar cutoffs against PostgreSQL."""

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.retention import cleanup
from app.retention.models import RetentionWindow
from app.retention.scopes import GLOBAL_ID, save_policy


async def test_native_guard_refuses_conflicting_jobs_before_row_deletion(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A conflict aborts the transaction before resolving any rows for deletion."""
    mocked = AsyncMock()
    mocked.scalar.side_effect = [True, 1]
    with pytest.raises(RuntimeError, match="Native retention jobs conflict"):
        await cleanup.guard_native_policies(mocked)
    assert mocked.scalar.await_count == 2


async def test_calendar_month_cutoff_is_not_a_fixed_thirty_days(session: AsyncSession) -> None:
    """Check rows one second either side of PostgreSQL's actual month boundary."""
    server = await session.scalar(text("""INSERT INTO collector.server(name,host,port,username,password)
        VALUES (:name,'localhost','5432','test','test') RETURNING id"""), {"name": uuid4().hex})
    await save_policy(session, "global", GLOBAL_ID, "*", RetentionWindow(value=1, unit="months"))
    await session.execute(text("""INSERT INTO metric.cpu(collected_at,server_id,cpu_percent)
        VALUES (now()-interval '1 month'+interval '1 second',:id,11),
               (now()-interval '1 month'-interval '1 second',:id,22),
               (now()-interval '1 month',:id,33)"""), {"id": server})
    assert await cleanup.delete_expired(session, server, "cpu") == 1
    assert sorted((await session.execute(text("SELECT cpu_percent FROM metric.cpu"))).scalars()) == [11, 33]


async def test_paused_rule_is_not_claimed_as_an_active_deletion_preview(session: AsyncSession) -> None:
    """Changing a paused rule's duration must not advertise an active cleanup."""
    from app.retention.scoped_preview import preview_scope

    await save_policy(session, "global", GLOBAL_ID, "cpu", RetentionWindow(value=7, unit="days"))
    await session.execute(text("UPDATE retention.policy SET enabled=false"))
    server = await session.scalar(text("""INSERT INTO collector.server(name,host,port,username,password)
        VALUES (:name,'localhost','5432','test','test') RETURNING id"""), {"name": uuid4().hex})
    await session.execute(text("INSERT INTO metric.cpu(collected_at,server_id) VALUES(now()-interval '100 days',:id)"), {"id": server})
    result = await preview_scope(session, "global", GLOBAL_ID, "cpu", RetentionWindow(value=1, unit="days"))
    assert result["expired_rows"] == 0
    assert result["tables"][0]["preserved"]


async def test_displayed_effective_rules_match_the_database_cleanup_resolution(session: AsyncSession) -> None:
    """The batched Settings view and the cleanup query must agree on inheritance."""
    from app.retention.scopes import list_settings, resolve_policy

    project = uuid4()
    await session.execute(text('INSERT INTO ingestion.project(id,name) VALUES (:id,:name)'), {'id': project, 'name': str(project)})
    server = (await session.execute(text("""INSERT INTO collector.server(name,host,port,username,password,ingestion_project_id)
        VALUES (:name,'localhost','5432','test','test',:project) RETURNING id,public_id,ingestion_project_id"""), {'name': uuid4().hex, 'project': project})).mappings().one()
    await save_policy(session, 'global', GLOBAL_ID, '*', RetentionWindow(value=90, unit='days'))
    await save_policy(session, 'project', project, 'cpu', RetentionWindow(value=30, unit='days'))
    await save_policy(session, 'server', server['public_id'], '*', RetentionWindow(value=7, unit='days'))
    settings = await list_settings(session)
    for effective in settings['effective']:
        assert effective['policy'] == await resolve_policy(session, dict(server), effective['name'])
