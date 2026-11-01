import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.collector.config_database import ConfigDatabase
from database.models.collector.config_server import ConfigServer
from database.models.collector.run import Run
from database.models.collector.server import Server
from database.models.metadata.database import Database
from database.models.metadata.table import Table
from database.models.metric.native_query import NativeQueryMetric
from utils import encrypt


@pytest_asyncio.fixture
async def recent_feature_database(
    db_session: AsyncSession,
) -> tuple[Server, Database, Table]:
    server = Server(
        name="Recent Feature Server",
        host="localhost",
        port="5432",
        username="postgres",
        password="password",
        public_id=uuid.uuid4(),
    )
    db_session.add(server)
    await db_session.flush()

    database = Database(
        server_id=server.id,
        db_name=encrypt("recent_features"),
        public_id=uuid.uuid4(),
    )
    db_session.add(database)
    await db_session.flush()

    table = Table(
        oid=81001,
        public_id=uuid.uuid4(),
        database_id=database.id,
        schema_name="public",
        name="orders",
    )
    db_session.add(table)
    await db_session.commit()
    return server, database, table


@pytest.mark.asyncio
async def test_query_analytics_supports_every_order(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    recent_feature_database: tuple[Server, Database, Table],
) -> None:
    _, database, _ = recent_feature_database
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.add_all(
        [
            NativeQueryMetric(
                collected_at=base + timedelta(minutes=1),
                database_id=database.id,
                pid=101,
                backend_start=base,
                query_start=base + timedelta(seconds=1),
                user_name="user",
                application_name="app",
                state="active",
                query="SELECT * FROM frequent_query",
                query_hash="frequent-1",
                query_duration_ms=10,
            ),
            NativeQueryMetric(
                collected_at=base + timedelta(minutes=2),
                database_id=database.id,
                pid=102,
                backend_start=base,
                query_start=base + timedelta(seconds=2),
                user_name="user",
                application_name="app",
                state="active",
                query="SELECT * FROM frequent_query",
                query_hash="frequent-2",
                query_duration_ms=10,
            ),
            NativeQueryMetric(
                collected_at=base + timedelta(minutes=3),
                database_id=database.id,
                pid=103,
                backend_start=base,
                query_start=base + timedelta(seconds=3),
                user_name="user",
                application_name="app",
                state="active",
                query="SELECT * FROM expensive_query",
                query_hash="expensive",
                query_duration_ms=100,
            ),
        ]
    )
    await db_session.commit()

    expected_first = {
        "executions": "frequent_query",
        "avg_duration": "expensive_query",
        "max_duration": "expensive_query",
        "total_duration": "expensive_query",
    }
    for order_by, expected in expected_first.items():
        response = await auth_client.get(
            f"/v1/databases/{database.public_id}/analytics/query",
            params={"preset": "1d", "order_by": order_by, "order_dir": "desc"},
        )
        assert response.status_code == 200
        assert expected in response.json()["items"][0]["query_signature"]

    invalid = await auth_client.get(
        f"/v1/databases/{database.public_id}/analytics/query",
        params={"preset": "1d", "order_by": "invalid"},
    )
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_run_history_filters_and_orders(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    recent_feature_database: tuple[Server, Database, Table],
) -> None:
    server, database, _ = recent_feature_database
    database_config = ConfigDatabase(
        database_id=database.id,
        name="slow_database_collector",
        interval=60,
        is_paused=False,
    )
    server_config = ConfigServer(
        server_id=server.id,
        name="fast_server_collector",
        interval=60,
        is_paused=False,
    )
    db_session.add_all([database_config, server_config])
    await db_session.flush()

    base = datetime.now(timezone.utc) - timedelta(hours=1)
    database_run = Run(
        config_database_id=database_config.id,
        status="failed",
        errors=["first", "second"],
        inserted_at=base + timedelta(minutes=10),
        finished_at=base + timedelta(minutes=20),
    )
    server_run = Run(
        config_server_id=server_config.id,
        status="success",
        errors=[],
        inserted_at=base,
        finished_at=base + timedelta(seconds=1),
    )
    db_session.add_all([database_run, server_run])
    await db_session.commit()

    response = await auth_client.get(
        f"/v1/databases/{database.public_id}/runs/history",
        params={
            "run_type": "database",
            "status": "failed",
            "name": "slow",
            "started_from": (base + timedelta(minutes=5)).isoformat(),
            "started_to": (base + timedelta(minutes=15)).isoformat(),
            "min_duration_seconds": 500,
            "max_duration_seconds": 700,
            "order_by": "duration",
            "order_dir": "desc",
        },
    )
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["slow_database_collector"]

    expected_first = {
        ("name", "asc"): "fast_server_collector",
        ("type", "desc"): "fast_server_collector",
        ("status", "asc"): "slow_database_collector",
        ("started_at", "asc"): "fast_server_collector",
        ("duration", "desc"): "slow_database_collector",
        ("errors", "desc"): "slow_database_collector",
    }
    for (order_by, order_dir), expected in expected_first.items():
        ordered = await auth_client.get(
            f"/v1/databases/{database.public_id}/runs/history",
            params={"order_by": order_by, "order_dir": order_dir},
        )
        assert ordered.status_code == 200
        assert ordered.json()[0]["name"] == expected
        second_page = await auth_client.get(
            f"/v1/databases/{database.public_id}/runs/history",
            params={"order_by": order_by, "order_dir": order_dir, "offset": 1, "limit": 1},
        )
        assert second_page.status_code == 200
        assert second_page.json() == ordered.json()[1:2]


@pytest.mark.asyncio
async def test_documentation_and_assignment_timeline_is_immutable(
    auth_client: AsyncClient,
    recent_feature_database: tuple[Server, Database, Table],
) -> None:
    server, database, table = recent_feature_database
    created_tag = await auth_client.post(
        "/v1/tags/",
        json={"server_id": str(server.public_id), "name": "Audited"},
    )
    assert created_tag.status_code == 201
    tag_id = created_tag.json()["id"]
    assignment = {
        "scope": "object",
        "target_type": "table",
        "target_id": str(table.public_id),
    }

    first_doc = await auth_client.put(
        f"/v1/databases/{database.public_id}/docs/tables/{table.public_id}",
        json={"description": "Initial documentation"},
    )
    second_doc = await auth_client.put(
        f"/v1/databases/{database.public_id}/docs/tables/{table.public_id}",
        json={"description": "Updated documentation"},
    )
    assert first_doc.status_code == 200
    assert second_doc.status_code == 200

    for _ in range(2):
        attached = await auth_client.post(
            f"/v1/tags/{tag_id}/assignments",
            json=assignment,
        )
        assert attached.status_code == 204
        listed = await auth_client.get(
            "/v1/tags/assignments",
            params={"database_id": str(database.public_id)},
        )
        assert any(item["tag"]["id"] == tag_id for item in listed.json())

        detached = await auth_client.request(
            "DELETE",
            f"/v1/tags/{tag_id}/assignments",
            json=assignment,
        )
        assert detached.status_code == 204
        listed = await auth_client.get(
            "/v1/tags/assignments",
            params={"database_id": str(database.public_id)},
        )
        assert all(item["tag"]["id"] != tag_id for item in listed.json())

    history = await auth_client.get(
        f"/v1/databases/{database.public_id}/schemas/history"
    )
    assert history.status_code == 200
    items = history.json()["items"]
    tag_actions = [item["action"] for item in items if item["type"] == "tag"]
    documentation_actions = [
        item["action"] for item in items if item["type"] == "documentation"
    ]
    assert tag_actions[:4] == ["unassigned", "assigned", "unassigned", "assigned"]
    assert documentation_actions[:2] == ["updated", "created"]


@pytest.mark.asyncio
async def test_assignment_rejects_a_tag_from_another_server(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    recent_feature_database: tuple[Server, Database, Table],
) -> None:
    server, _, _ = recent_feature_database
    other_server = Server(
        name="Other Server",
        host="localhost",
        port="5432",
        username="postgres",
        password="password",
        public_id=uuid.uuid4(),
    )
    db_session.add(other_server)
    await db_session.flush()
    other_database = Database(
        server_id=other_server.id,
        db_name=encrypt("other_database"),
        public_id=uuid.uuid4(),
    )
    db_session.add(other_database)
    await db_session.commit()

    created_tag = await auth_client.post(
        "/v1/tags/",
        json={"server_id": str(server.public_id), "name": "Server Local"},
    )
    response = await auth_client.post(
        f"/v1/tags/{created_tag.json()['id']}/assignments",
        json={
            "scope": "object",
            "target_type": "database",
            "target_id": str(other_database.public_id),
        },
    )
    assert response.status_code == 400
