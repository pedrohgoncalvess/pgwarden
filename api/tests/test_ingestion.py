"""Exercise ingestion against an explicitly configured disposable PostgreSQL.

Set INGESTION_TEST_DATABASE_URL to a local administrative test connection. The
fixture creates and removes its own randomly named database. Timescale-only
DDL is omitted from the baseline; new migrations and every endpoint use real
PostgreSQL transactions and the existing collector/metric tables.
"""

import os
import re
import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import psycopg
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from psycopg import sql
from sqlalchemy import select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from yoyo import get_backend, read_migrations
from app.auth.services import get_current_user
from app.ingestion.router import router as ingestion_router
from app.projects.router import router as projects_router
from app.projects.rotation import rotate_due_keys
from app.projects.tables import api_key, entity, event, project
from database.connection import DatabaseConnection

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _stub_embeddings() -> Iterator[None]:
    """These routes do not use embeddings or the wider application bootstrap."""
    yield


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    url = os.getenv("INGESTION_TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set INGESTION_TEST_DATABASE_URL for disposable PostgreSQL integration tests"
        )
    database_name = "pgwarden_ingestion_" + uuid4().hex
    admin = psycopg.connect(url, autocommit=True)
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    database_url = (
        make_url(url).set(database=database_name).render_as_string(hide_password=False)
    )
    backend = None
    try:
        with psycopg.connect(database_url, autocommit=True) as connection:
            for filename in [
                "20260324_01_pUn2z.sql",
                "20260424_01_9UN1w-add-n-mod-since-analyze.sql",
                "20260623_01_database-stats-metric.sql",
                "20260624_01_native-query-metric.sql",
            ]:
                ddl = (ROOT / "migrations/sql" / filename).read_text()
                ddl = re.sub(
                    "CREATE EXTENSION IF NOT EXISTS (timescaledb|vector);", "", ddl
                )
                ddl = re.sub("SELECT create_hypertable\\([^;]+;", "", ddl)
                connection.execute(ddl)
        directory = tmp_path_factory.mktemp("ingestion-migration")
        for path in (ROOT / "migrations/sql").glob(
            "20261030_01_ingestion-projects*.sql"
        ):
            content = re.sub("-- depends:.*", "-- depends:", path.read_text(), count=1)
            (directory / path.name).write_text(content)
        backend = get_backend(
            make_url(database_url)
            .set(drivername="postgresql+psycopg")
            .render_as_string(hide_password=False)
        )
        migrations = read_migrations(str(directory))
        with backend.lock():
            backend.apply_migrations(backend.to_apply(migrations))
        assert not backend.to_apply(migrations)
        yield database_url
        with backend.lock():
            backend.rollback_migrations(backend.to_rollback(migrations))
        assert backend.to_apply(migrations)
        assert (
            backend.connection.execute(
                "SELECT to_regnamespace('ingestion')"
            ).fetchone()[0]
            is None
        )
    finally:
        if backend:
            backend.connection.close()
        admin.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                sql.Identifier(database_name)
            )
        )
        admin.close()


@pytest_asyncio.fixture
async def db_session(
    _apply_migrations: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncSession]:
    url = make_url(_apply_migrations).set(drivername="postgresql+asyncpg")
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        async def enter(self: DatabaseConnection) -> AsyncSession:
            return session

        async def exit(self: DatabaseConnection, *args: Any) -> None:
            return None

        monkeypatch.setattr(DatabaseConnection, "__aenter__", enter)
        monkeypatch.setattr(DatabaseConnection, "__aexit__", exit)
        monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
        yield session
        await session.close()
        await transaction.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(projects_router, prefix="/v1")
    app.include_router(ingestion_router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(is_admin=True)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        yield client


async def provision(client: AsyncClient, **settings: Any) -> dict:
    response = await client.post("/v1/projects", json={"name": uuid4().hex, **settings})
    assert response.status_code == 201, response.text
    return response.json()


def item(table: str, data: dict, local_id: int | None = None, **changes: Any) -> dict:
    return {
        "event_id": str(uuid4()),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "table": table,
        "local_id": local_id,
        "data": data,
        **changes,
    }


def batch(*events: Any, source_id: str | None = None) -> dict:
    return {
        "version": 1,
        "source_id": source_id or str(uuid4()),
        "events": list(events),
    }


async def send(client: AsyncClient, key: str, body: dict) -> Response:
    return await client.post(
        "/v1/ingestion/events", headers={"Authorization": f"Bearer {key}"}, json=body
    )


@pytest.mark.asyncio
async def test_project_secrets_defaults_and_optional_policies(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await provision(client)
    assert created["project"]["key_expiration_days"] is None
    assert created["project"]["rotation_interval_days"] is None
    assert created["credential"]["metadata"]["expires_at"] is None
    key = created["credential"]["key"]
    assert len(key) >= 40
    response = await client.get(f"/v1/projects/{created['project']['id']}/keys")
    assert response.status_code == 200
    assert (
        key not in response.text
        and "key_hash" not in response.text
        and ("encrypted_secret" not in response.text)
    )
    stored = (await db_session.execute(select(api_key))).mappings().one()
    assert stored["key_hash"] != key and stored["encrypted_secret"] is None
    assert response.headers["cache-control"] == "no-store"
    expiring = await provision(
        client, key_expiration_days=90, rotation_interval_days=30
    )
    assert expiring["credential"]["metadata"]["expires_at"] is not None
    assert expiring["project"]["next_rotation_at"] is not None


@pytest.mark.asyncio
async def test_policies_admin_authorization_and_duplicate_names(
    client: AsyncClient,
) -> None:
    for settings in [
        {"key_expiration_days": 0},
        {"rotation_interval_days": 2, "key_expiration_days": 1},
        {"rotation_interval_days": 1, "rotation_grace_hours": 0},
        {"name": " "},
    ]:
        response = await client.post("/v1/projects", json={"name": "test", **settings})
        assert response.status_code == 422
    await provision(client, name="unique")
    assert (
        await client.post("/v1/projects", json={"name": "unique"})
    ).status_code == 409
    app = client._transport.app
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(is_admin=False)
    assert (await client.get("/v1/projects")).status_code == 403
    app.dependency_overrides.clear()
    assert (await client.get("/v1/projects")).status_code == 401


@pytest.mark.asyncio
async def test_receive_maps_entities_and_metrics_and_deduplicates(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await provision(client)
    key = created["credential"]["key"]
    timestamp = datetime.now(timezone.utc).isoformat()
    body = batch(
        item("collector_server", {"name": "production"}, 1),
        item("metadata_database", {"server_id": 1, "db_name": "app"}, 1),
        item(
            "metadata_table",
            {"database_id": 1, "oid": 123, "schema_name": "public", "name": "users"},
            1,
        ),
        item(
            "metric_cpu",
            {
                "server_id": 1,
                "collected_at": timestamp,
                "cpu_percent": 42.5,
                "cpu_count": 4,
            },
        ),
        item(
            "metric_database_stat",
            {"database_id": 1, "collected_at": timestamp, "xact_commit": 100},
        ),
    )
    response = await send(client, key, body)
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] == 5
    assert response.json()["acknowledged_event_ids"] == [
        row["event_id"] for row in body["events"]
    ]
    assert response.headers["cache-control"] == "no-store"
    response = await send(client, key, body)
    assert response.json()["accepted"] == 0 and response.json()["duplicates"] == 5
    assert (
        await db_session.execute(text("SELECT count(*) FROM metric.cpu"))
    ).scalar_one() == 1
    assert (await db_session.execute(select(event))).mappings().all()
    assert (
        await db_session.execute(
            text("SELECT ingestion_project_id FROM collector.server")
        )
    ).scalar_one() is not None
    changed = {**body, "events": [{**body["events"][0], "data": {"name": "different"}}]}
    assert (await send(client, key, changed)).status_code == 409


@pytest.mark.asyncio
async def test_bad_batch_rolls_back_every_event_and_missing_parent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await provision(client)
    body = batch(
        item("collector_server", {"name": "rollback"}, 1),
        item(
            "metric_cpu",
            {"server_id": 999, "collected_at": datetime.now(timezone.utc).isoformat()},
        ),
    )
    response = await send(client, created["credential"]["key"], body)
    assert response.status_code == 409
    assert (await db_session.execute(select(event))).first() is None
    assert (await db_session.execute(select(entity))).first() is None
    assert (
        await db_session.execute(text("SELECT count(*) FROM collector.server"))
    ).scalar_one() == 0
    body["events"][1]["data"] = {"server_id": 1, "collected_at": "not-a-timestamp"}
    assert (await send(client, created["credential"]["key"], body)).status_code == 422
    assert (await db_session.execute(select(event))).first() is None


@pytest.mark.asyncio
async def test_project_source_isolation_and_stale_snapshots(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    first, second = (await provision(client), await provision(client))
    source = str(uuid4())
    initial = batch(
        item("collector_server", {"name": "same-local-id"}, 1), source_id=source
    )
    assert (await send(client, first["credential"]["key"], initial)).status_code == 200
    assert (await send(client, second["credential"]["key"], initial)).status_code == 200
    rows = (await db_session.execute(select(entity))).mappings().all()
    assert len({row["central_id"] for row in rows}) == 2
    missing_source = batch(
        item(
            "metric_cpu",
            {"server_id": 1, "collected_at": datetime.now(timezone.utc).isoformat()},
        )
    )
    assert (
        await send(client, first["credential"]["key"], missing_source)
    ).status_code == 409
    stale = batch(
        item(
            "collector_server",
            {"name": "stale"},
            1,
            occurred_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        ),
        source_id=source,
    )
    assert (await send(client, first["credential"]["key"], stale)).status_code == 200
    assert not (
        await db_session.execute(
            text("SELECT name FROM collector.server WHERE name LIKE '%stale%'")
        )
    ).first()


@pytest.mark.asyncio
async def test_manual_rotation_revoke_expiration_and_disable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await provision(client)
    project_id = created["project"]["id"]
    body = batch(item("collector_server", {"name": "rotated"}, 1))
    old = created["credential"]["key"]
    rotated = await client.post(
        f"/v1/projects/{project_id}/keys/rotate", json={"grace_hours": 0}
    )
    assert rotated.status_code == 200
    new = rotated.json()["key"]
    assert (await send(client, old, body)).status_code == 401
    assert (await send(client, new, body)).status_code == 200
    key_id = rotated.json()["metadata"]["id"]
    from uuid import UUID

    await db_session.execute(
        update(api_key)
        .where(api_key.c.id == UUID(key_id))
        .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    )
    await db_session.commit()
    assert (await send(client, new, body)).status_code == 401
    fresh = (
        await client.post(f"/v1/projects/{project_id}/keys/rotate", json={})
    ).json()
    assert (
        await client.delete(f"/v1/projects/{project_id}/keys/{fresh['metadata']['id']}")
    ).status_code == 204
    assert (await send(client, fresh["key"], body)).status_code == 401


@pytest.mark.asyncio
async def test_automatic_rotation_handoff_retries_and_retirement(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await provision(client, rotation_interval_days=1, key_expiration_days=30)
    from uuid import UUID

    project_id = UUID(created["project"]["id"])
    await db_session.execute(
        update(project)
        .where(project.c.id == project_id)
        .values(next_rotation_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    )
    await db_session.commit()
    assert await rotate_due_keys(db_session) == 1
    assert await rotate_due_keys(db_session) == 0
    body = batch(item("collector_server", {"name": "automatic"}, 1))
    response = await send(client, created["credential"]["key"], body)
    assert response.status_code == 200, response.text
    replacement = response.json()["replacement_key"]
    assert replacement and replacement != created["credential"]["key"]
    assert (await send(client, created["credential"]["key"], body)).json()[
        "replacement_key"
    ] == replacement
    assert (await send(client, replacement, body)).json()["replacement_key"] is None
    await db_session.execute(
        update(api_key)
        .where(api_key.c.project_id == project_id, api_key.c.retire_at.is_not(None))
        .values(retire_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    )
    await db_session.commit()
    assert (await send(client, created["credential"]["key"], body)).status_code == 401
    assert await rotate_due_keys(db_session) == 0
    current = (
        (
            await db_session.execute(
                select(api_key).where(
                    api_key.c.project_id == project_id, api_key.c.retire_at.is_(None)
                )
            )
        )
        .mappings()
        .one()
    )
    assert current["encrypted_secret"] is None


@pytest.mark.asyncio
async def test_malformed_oversized_and_privileged_events_are_rejected(
    client: AsyncClient,
) -> None:
    created = await provision(client)
    key = created["credential"]["key"]
    assert (await client.post("/v1/ingestion/events", json={})).status_code == 401
    assert (
        await send(client, key, {"source_id": str(uuid4()), "events": []})
    ).status_code == 422
    body = batch(
        item(
            "collector_server", {"name": "unsafe", "password": "must-not-be-stored"}, 1
        )
    )
    assert (await send(client, key, body)).status_code == 422
    body["events"][0]["table"] = "base_user"
    assert (await send(client, key, body)).status_code == 422
    response = await client.post(
        "/v1/ingestion/events",
        headers={"Authorization": f"Bearer {key}"},
        content=b"x" * (2 * 1024 * 1024 + 1),
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_all_metric_types_and_index_relationships(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.ingestion.catalog import TABLES

    created = await provision(client)
    key = created["credential"]["key"]
    now = datetime.now(timezone.utc).isoformat()
    parents = [
        item("collector_server", {"name": "all-metrics"}, 1),
        item("metadata_database", {"server_id": 1, "db_name": "app"}, 1),
        item(
            "metadata_table",
            {"database_id": 1, "oid": 11, "schema_name": "public", "name": "users"},
            1,
        ),
        item(
            "metadata_column",
            {"table_id": 1, "name": "id", "data_type": "bigint", "ordinal_position": 1},
            1,
        ),
        item(
            "metadata_index",
            {
                "database_id": 1,
                "table_id": 1,
                "oid": 12,
                "name": "users_pk",
                "type": "btree",
                "definition": "CREATE INDEX users_pk ON users (id)",
            },
            1,
        ),
        item(
            "metadata_index_column",
            {"index_id": 1, "column_id": 1, "ordinal_position": 1},
        ),
    ]
    values = {
        "server_id": 1,
        "database_id": 1,
        "table_id": 1,
        "column_id": 1,
        "index_id": 1,
        "collected_at": now,
        "backend_start": now,
        "pid": 5,
        "holder_pid": 5,
        "mount_point": "/",
        "type": "relation",
        "mode": "AccessShareLock",
        "size": 512,
    }
    observations = []
    for name, table in TABLES.items():
        if not name.startswith("metric_"):
            continue
        data = {
            column.name: values[column.name]
            for column in table.columns
            if column.name in values
        }
        if name == "metric_native_query":
            data.update(
                usesysid=16384,
                client_addr="2001:db8::1",
                query_duration_ms=1.25,
                query="SELECT 1",
            )
        if name == "metric_table":
            data["modifications_since_last_analyze"] = 10
        observations.append(item(name, data))
    body = batch(*parents, *observations)
    response = await send(client, key, body)
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] == len(parents) + 11
    for name, table in TABLES.items():
        if name.startswith("metric_"):
            assert (await db_session.execute(select(table))).first() is not None
    deletion = batch(
        item(
            "metadata_index_column",
            {"index_id": 1, "column_id": 1, "ordinal_position": 1},
            operation="delete",
        ),
        source_id=body["source_id"],
    )
    assert (await send(client, key, deletion)).status_code == 200
    assert (
        await db_session.execute(text("SELECT count(*) FROM metadata.index_column"))
    ).scalar_one() == 0


@pytest.mark.asyncio
async def test_disable_project_and_ingestion_keys_cannot_manage_projects(
    client: AsyncClient,
) -> None:
    from app.projects.models import ProjectSettings

    created = await provision(client)
    settings = {
        field: created["project"][field] for field in ProjectSettings.model_fields
    }
    response = await client.put(
        f"/v1/projects/{created['project']['id']}", json={**settings, "enabled": False}
    )
    assert response.status_code == 200
    body = batch(item("collector_server", {"name": "disabled"}, 1))
    assert (await send(client, created["credential"]["key"], body)).status_code == 401
    client._transport.app.dependency_overrides.clear()
    assert (
        await client.get(
            "/v1/projects",
            headers={"Authorization": f"Bearer {created['credential']['key']}"},
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_revoked_current_key_is_not_recreated_by_scheduler(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from uuid import UUID

    created = await provision(client, rotation_interval_days=1)
    project_id = created["project"]["id"]
    key_id = created["credential"]["metadata"]["id"]
    assert (
        await client.delete(f"/v1/projects/{project_id}/keys/{key_id}")
    ).status_code == 204
    await db_session.execute(
        update(project)
        .where(project.c.id == UUID(project_id))
        .values(next_rotation_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    )
    await db_session.commit()
    assert await rotate_due_keys(db_session) == 0
    assert len((await db_session.execute(select(api_key))).all()) == 1


@pytest.mark.asyncio
async def test_public_openapi_documents_event_schema_without_dangling_refs(
    client: AsyncClient,
) -> None:
    schema = (await client.get("/openapi.json")).json()
    body = schema["paths"]["/v1/ingestion/events"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert (
        body["properties"]["events"]["items"]["properties"]["event_id"]["format"]
        == "uuid"
    )


@pytest.mark.asyncio
async def test_concurrent_delivery_and_rotation_use_project_locks(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID

    engine = create_async_engine(db_session.bind.engine.url, poolclass=NullPool)

    async def enter(self: DatabaseConnection) -> AsyncSession:
        self._ingestion_session = AsyncSession(engine, expire_on_commit=False)
        return self._ingestion_session

    async def exit(self: DatabaseConnection, *args: Any) -> None:
        await self._ingestion_session.close()

    monkeypatch.setattr(DatabaseConnection, "__aenter__", enter)
    monkeypatch.setattr(DatabaseConnection, "__aexit__", exit)
    project_id = None
    try:
        created = await provision(client, rotation_interval_days=1)
        project_id = UUID(created["project"]["id"])
        body = batch(
            item("collector_server", {"name": "concurrent"}, 1),
            item(
                "metric_cpu",
                {
                    "server_id": 1,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                    "cpu_percent": 10,
                },
            ),
        )
        responses = await asyncio.gather(
            *(send(client, created["credential"]["key"], body) for _ in range(2))
        )
        assert all((response.status_code == 200 for response in responses))
        assert sorted((response.json()["accepted"] for response in responses)) == [0, 2]
        async with AsyncSession(engine) as session:
            await session.execute(
                update(project)
                .where(project.c.id == project_id)
                .values(
                    next_rotation_at=datetime.now(timezone.utc) - timedelta(seconds=1)
                )
            )
            await session.commit()
        async with AsyncSession(engine) as first, AsyncSession(engine) as second:
            assert (
                sum(
                    await asyncio.gather(
                        rotate_due_keys(first), rotate_due_keys(second)
                    )
                )
                == 1
            )
        async with AsyncSession(engine) as session:
            current = (
                await session.execute(
                    select(api_key).where(
                        api_key.c.project_id == project_id,
                        api_key.c.revoked_at.is_(None),
                        api_key.c.retire_at.is_(None),
                    )
                )
            ).all()
            assert len(current) == 1
    finally:
        if project_id:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM collector.server WHERE ingestion_project_id=:id"),
                    {"id": project_id},
                )
                await connection.execute(
                    project.delete().where(project.c.id == project_id)
                )
        await engine.dispose()
