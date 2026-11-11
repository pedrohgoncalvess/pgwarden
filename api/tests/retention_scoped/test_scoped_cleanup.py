"""Prove retention by checking rows actually deleted from disposable PostgreSQL."""

from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.services import get_current_user
from app.retention.cleanup import delete_expired
from app.retention.models import RetentionWindow
from app.retention.ownership import TABLE_NAMES, get_owner
from app.retention.scope_router import router
from app.retention.scopes import GLOBAL_ID, remove_policy, resolve_policy, save_policy
from app.retention.scoped_preview import preview_scope
from app.retention.services import update_policy


def window(value: int, unit: str = "days") -> RetentionWindow:
    """Construct a validated retention interval."""
    return RetentionWindow(value=value, unit=unit)


@pytest_asyncio.fixture
async def fleet(session: AsyncSession) -> dict[str, Any]:
    """Create two projects and four servers, one without a project."""
    projects = [uuid4(), uuid4()]
    for project in projects:
        await session.execute(text("INSERT INTO ingestion.project(id,name) VALUES (:id,:name)"),
                              {"id": project, "name": str(project)})
    servers = []
    for index, project in enumerate([projects[0], projects[0], projects[1], None]):
        server = (await session.execute(text("""
            INSERT INTO collector.server(name,host,port,username,password,ingestion_project_id)
            VALUES (:name,'localhost','5432','test','test',:project)
            RETURNING id,public_id,ingestion_project_id
        """), {"name": f"server-{index}", "project": project})).mappings().one()
        servers.append(dict(server))
    return {"projects": projects, "servers": servers}


async def insert_cpu(session: AsyncSession, server: int, age: str) -> None:
    """Insert metric data at a PostgreSQL calendar-relative timestamp."""
    await session.execute(text("""INSERT INTO metric.cpu(collected_at,server_id,cpu_percent)
        VALUES(now()-CAST(CAST(:age AS text) AS interval),:server,10)"""), {"age": age, "server": server})


async def count_cpu(session: AsyncSession, server: int) -> int:
    """Read retained data rather than inspecting generated SQL."""
    return await session.scalar(text("SELECT count(*) FROM metric.cpu WHERE server_id=:id"), {"id": server})


async def test_actual_deletion_obeys_server_project_and_global(
    session: AsyncSession, fleet: dict[str, Any],
) -> None:
    """Different servers sharing one metric table retain different history."""
    servers = fleet["servers"]
    await save_policy(session, "global", GLOBAL_ID, "*", window(90))
    await save_policy(session, "project", fleet["projects"][0], "*", window(30))
    await save_policy(session, "server", servers[0]["public_id"], "*", window(7))
    for server in servers:
        for age in ("2 days", "10 days", "40 days", "100 days"):
            await insert_cpu(session, server["id"], age)
    for server, expected_deleted in zip(servers, [3, 2, 1, 1]):
        assert await delete_expired(session, server["id"], "cpu") == expected_deleted
    assert [await count_cpu(session, server["id"]) for server in servers] == [1, 2, 3, 3]


async def test_longer_server_override_survives_shorter_global_and_legacy_update(
    session: AsyncSession, fleet: dict[str, Any],
) -> None:
    """The old table endpoint cannot create a destructive native policy."""
    server = fleet["servers"][0]
    await save_policy(session, "server", server["public_id"], "*", window(180))
    await update_policy(session, "cpu", window(7))
    await insert_cpu(session, server["id"], "100 days")
    await insert_cpu(session, server["id"], "200 days")
    assert await delete_expired(session, server["id"], "cpu") == 1
    assert await count_cpu(session, server["id"]) == 1
    effective = await resolve_policy(session, server, "cpu")
    assert effective["scope"] == "server"
    assert effective["duration"] == timedelta(days=180)


async def test_override_removal_restores_inheritance_and_changes_real_cleanup(
    session: AsyncSession, fleet: dict[str, Any],
) -> None:
    """Removing an exception makes previously protected history expire."""
    server = fleet["servers"][0]
    await save_policy(session, "project", fleet["projects"][0], "*", window(7))
    await save_policy(session, "server", server["public_id"], "*", window(30))
    await insert_cpu(session, server["id"], "10 days")
    assert await delete_expired(session, server["id"], "cpu") == 0
    await remove_policy(session, "server", server["public_id"], "*")
    assert await delete_expired(session, server["id"], "cpu") == 1
    assert await count_cpu(session, server["id"]) == 0


async def test_table_rules_and_scope_priority(session: AsyncSession, fleet: dict[str, Any]) -> None:
    """A server-wide rule takes precedence over a project's table-specific rule."""
    server = fleet["servers"][0]
    await save_policy(session, "global", GLOBAL_ID, "cpu", window(90))
    await save_policy(session, "project", fleet["projects"][0], "cpu", window(60))
    await save_policy(session, "server", server["public_id"], "*", window(30))
    await insert_cpu(session, server["id"], "40 days")
    assert await delete_expired(session, server["id"], "cpu") == 1
    await save_policy(session, "server", server["public_id"], "cpu", window(7))
    await insert_cpu(session, server["id"], "10 days")
    assert await delete_expired(session, server["id"], "cpu") == 1


@pytest.mark.parametrize("unit,inside,outside", [
    ("minutes", "30 seconds", "2 minutes"), ("hours", "30 minutes", "2 hours"),
    ("days", "12 hours", "2 days"), ("weeks", "6 days", "8 days"),
    ("months", "27 days", "32 days"),
])
async def test_every_unit_enforces_actual_expiry(
    session: AsyncSession, fleet: dict[str, Any], unit: str, inside: str, outside: str,
) -> None:
    """Use PostgreSQL intervals for every supported duration unit."""
    server = fleet["servers"][0]
    await save_policy(session, "server", server["public_id"], "*", window(1, unit))
    await insert_cpu(session, server["id"], inside)
    await insert_cpu(session, server["id"], outside)
    assert await delete_expired(session, server["id"], "cpu") == 1
    assert await count_cpu(session, server["id"]) == 1


async def test_batches_boundary_paused_and_missing_policies(
    session: AsyncSession, fleet: dict[str, Any],
) -> None:
    """Bound work and keep boundary rows, paused scopes and unlimited history."""
    server = fleet["servers"][0]
    await insert_cpu(session, server["id"], "100 days")
    assert await delete_expired(session, server["id"], "cpu") == 0
    await save_policy(session, "global", GLOBAL_ID, "*", window(7))
    await session.execute(text("UPDATE retention.policy SET enabled=false"))
    assert await delete_expired(session, server["id"], "cpu") == 0
    await session.execute(text("UPDATE retention.policy SET enabled=true"))
    for age in ("8 days", "9 days", "7 days"):
        await insert_cpu(session, server["id"], age)
    assert await delete_expired(session, server["id"], "cpu", batch_size=2) == 2
    assert await delete_expired(session, server["id"], "cpu", batch_size=2) == 1
    assert await count_cpu(session, server["id"]) == 1
    assert await session.scalar(text("SELECT count(*) FROM retention.run")) == 1


async def test_soft_deleted_and_reassigned_servers(
    session: AsyncSession, fleet: dict[str, Any],
) -> None:
    """Use current project ownership and continue purging soft-deleted servers."""
    server = fleet["servers"][0]
    await save_policy(session, "project", fleet["projects"][0], "*", window(30))
    await save_policy(session, "project", fleet["projects"][1], "*", window(7))
    await insert_cpu(session, server["id"], "10 days")
    assert await delete_expired(session, server["id"], "cpu") == 0
    await session.execute(text("UPDATE collector.server SET ingestion_project_id=:project,deleted_at=now() WHERE id=:id"), {"project": fleet["projects"][1], "id": server["id"]})
    assert await delete_expired(session, server["id"], "cpu") == 1


async def test_preview_preserves_overrides_and_does_not_delete(
    session: AsyncSession, fleet: dict[str, Any],
) -> None:
    """Project/global previews do not claim data protected by server exceptions."""
    first, second = fleet["servers"][:2]
    await save_policy(session, "server", first["public_id"], "*", window(180))
    for server in (first, second):
        await insert_cpu(session, server["id"], "100 days")
    preview = await preview_scope(session, "project", fleet["projects"][0], "cpu", window(7))
    assert preview["expired_rows"] == 1
    assert preview["tables"][0]["preserved"]
    assert await count_cpu(session, first["id"]) == 1
    assert await count_cpu(session, second["id"]) == 1


async def test_all_actual_metric_ownership_paths(
    session: AsyncSession, fleet: dict[str, Any],
) -> None:
    """Compile ownership expressions against every real migrated metric schema."""
    for name in TABLE_NAMES:
        await session.execute(text(f'SELECT {get_owner(name)} FROM metric."{name}" m LIMIT 1'))


async def test_api_validates_targets_and_rejects_non_admin(
    session: AsyncSession, fleet: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise real HTTP policy updates, inheritance and permissions."""
    from app.retention import scope_router

    @asynccontextmanager
    async def connection() -> Any:
        yield session

    monkeypatch.setattr(scope_router, "DatabaseConnection", connection)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(is_admin=True)
    target = fleet["servers"][0]["public_id"]
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        response = await client.put(f"/retention/scopes/server/{target}/*", json={"value": 7, "unit": "days"})
        assert response.status_code == 200, response.text
        effective = next(item for item in response.json()["effective"] if item["server_id"] == str(target))
        assert effective["policy"]["scope"] == "server"
        assert (await client.put(f"/retention/scopes/server/{uuid4()}/*", json={"value": 1, "unit": "days"})).status_code == 404
        assert (await client.put(f"/retention/scopes/server/{target}/*", json={"value": 0, "unit": "days"})).status_code == 422
        assert (await client.put(f"/retention/scopes/server/{target}/unknown", json={"value": 1, "unit": "days"})).status_code == 404
        assert (await client.delete(f"/retention/scopes/server/{target}/*")).status_code == 204
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(is_admin=False)
        for method, path in [("GET", ""), ("PUT", f"/server/{target}/*"), ("DELETE", f"/server/{target}/*"), ("POST", f"/server/{target}/*/preview")]:
            response = await client.request(method, "/retention/scopes"+path, json={"value": 1, "unit": "days"})
            assert response.status_code == 403
