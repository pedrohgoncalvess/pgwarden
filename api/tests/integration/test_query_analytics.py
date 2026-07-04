import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.databases.analytics.query.services import _normalize_query
from database.models.collector.server import Server
from database.models.metadata.database import Database
from database.models.metric.native_query import NativeQueryMetric
from utils import encrypt


@pytest.mark.parametrize(
    "query,expected",
    [
        ('SELECT * FROM "base"."user"', "select * from base.user"),
        ("SELECT id, name FROM t WHERE x = 1 AND y = 'foo'", "select id, name from t where x = ? and y = ?"),
        ("SELECT * FROM t WHERE id IN (1,2,3)", "select * from t where id in (?)"),
        ("-- comment\nSELECT * FROM t;", "select * from t"),
        ("/* block\ncomment */ SELECT /* inline */ 1 FROM t", "select ? from t"),
        ('SELECT * FROM "t" WHERE a = -3.14', "select * from t where a = ?"),
        ("  SELECT   *   FROM   t   ", "select * from t"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_query(query, expected):
    assert _normalize_query(query) == expected


@pytest_asyncio.fixture
async def test_server_and_database(db_session):
    server = Server(
        name="Test Server",
        host="localhost",
        port="5432",
        username="postgres",
        password="password",
        public_id=uuid.uuid4(),
    )
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)

    database = Database(
        server_id=server.id,
        db_name=encrypt("analytics_db"),
        public_id=uuid.uuid4(),
    )
    db_session.add(database)
    await db_session.commit()
    await db_session.refresh(database)

    return server, database


@pytest.mark.asyncio
async def test_query_analytics_aggregates(
    auth_client: AsyncClient,
    db_session,
    test_server_and_database,
):
    _, database = test_server_and_database
    now = datetime.now(timezone.utc)
    base = now - timedelta(hours=1)

    # Two executions of the same logical query, one by user_a and one by user_b.
    # The first execution has two snapshots (should count as one execution).
    rows = [
        NativeQueryMetric(
            collected_at=base + timedelta(minutes=1),
            database_id=database.id,
            pid=100,
            backend_start=base,
            query_start=base + timedelta(seconds=10),
            user_name="user_a",
            application_name="app_1",
            state="active",
            query='SELECT * FROM "base"."user" WHERE id = 1',
            query_hash="hash1",
            query_duration_ms=100.0,
        ),
        NativeQueryMetric(
            collected_at=base + timedelta(minutes=1, seconds=30),
            database_id=database.id,
            pid=100,
            backend_start=base,
            query_start=base + timedelta(seconds=10),
            user_name="user_a",
            application_name="app_1",
            state="active",
            query='SELECT * FROM "base"."user" WHERE id = 2',
            query_hash="hash1",
            query_duration_ms=150.0,
        ),
        NativeQueryMetric(
            collected_at=base + timedelta(minutes=3),
            database_id=database.id,
            pid=200,
            backend_start=base,
            query_start=base + timedelta(minutes=2),
            user_name="user_b",
            application_name="app_2",
            state="idle",
            query='SELECT * FROM base.user WHERE id = 3',
            query_hash="hash1",
            query_duration_ms=200.0,
        ),
        # A completely different query.
        NativeQueryMetric(
            collected_at=base + timedelta(minutes=4),
            database_id=database.id,
            pid=300,
            backend_start=base,
            query_start=base + timedelta(minutes=3),
            user_name="user_a",
            application_name="app_1",
            state="active",
            query="DELETE FROM logs WHERE created_at < '2024-01-01'",
            query_hash="hash2",
            query_duration_ms=500.0,
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()

    response = await auth_client.get(f"/v1/databases/{database.public_id}/analytics/query?preset=1d")
    assert response.status_code == 200
    data = response.json()

    assert data["database_id"] == str(database.public_id)
    assert data["database_name"] == "analytics_db"
    assert data["total"] == 2
    assert len(data["items"]) == 2

    select_item = next(i for i in data["items"] if i["query_signature"] == "select * from base.user where id = ?")
    assert select_item["execution_count"] == 2
    assert select_item["unique_users"] == 2
    assert select_item["unique_applications"] == 2
    # Avg of per-execution averages: (125.0 + 200.0) / 2
    assert select_item["avg_duration_ms"] == pytest.approx(162.5, rel=1e-3)
    assert select_item["total_duration_ms"] == pytest.approx(325.0, rel=1e-3)
    assert select_item["max_duration_ms"] == pytest.approx(200.0, rel=1e-3)
    assert select_item["min_duration_ms"] == pytest.approx(125.0, rel=1e-3)

    delete_item = next(i for i in data["items"] if "delete" in i["query_signature"])
    assert delete_item["execution_count"] == 1

    assert len(data["timeline"]) >= 1
    assert data["filters"]["users"] == ["user_a", "user_b"]
    assert data["filters"]["applications"] == ["app_1", "app_2"]
    assert set(data["filters"]["states"]) == {"active", "idle"}


@pytest.mark.asyncio
async def test_query_analytics_filters(
    auth_client: AsyncClient,
    db_session,
    test_server_and_database,
):
    _, database = test_server_and_database
    now = datetime.now(timezone.utc)
    base = now - timedelta(hours=1)

    rows = [
        NativeQueryMetric(
            collected_at=base + timedelta(minutes=1),
            database_id=database.id,
            pid=100,
            backend_start=base,
            user_name="user_a",
            application_name="app_1",
            state="active",
            query="SELECT 1",
            query_hash="hash1",
            query_duration_ms=10.0,
        ),
        NativeQueryMetric(
            collected_at=base + timedelta(minutes=2),
            database_id=database.id,
            pid=200,
            backend_start=base,
            user_name="user_b",
            application_name="app_2",
            state="active",
            query="SELECT 2",
            query_hash="hash2",
            query_duration_ms=20.0,
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()

    response = await auth_client.get(
        f"/v1/databases/{database.public_id}/analytics/query?preset=1d&user_name=user_a"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["query_signature"] == "select ?"
    assert data["items"][0]["execution_count"] == 1


@pytest.mark.asyncio
async def test_query_analytics_search(
    auth_client: AsyncClient,
    db_session,
    test_server_and_database,
):
    _, database = test_server_and_database
    now = datetime.now(timezone.utc)
    base = now - timedelta(hours=1)

    rows = [
        NativeQueryMetric(
            collected_at=base + timedelta(minutes=1),
            database_id=database.id,
            pid=100,
            backend_start=base,
            user_name="user_a",
            application_name="app_1",
            state="active",
            query="SELECT * FROM users",
            query_hash="hash1",
            query_duration_ms=10.0,
        ),
        NativeQueryMetric(
            collected_at=base + timedelta(minutes=2),
            database_id=database.id,
            pid=200,
            backend_start=base,
            user_name="user_b",
            application_name="app_2",
            state="active",
            query="DELETE FROM logs",
            query_hash="hash2",
            query_duration_ms=20.0,
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()

    response = await auth_client.get(
        f"/v1/databases/{database.public_id}/analytics/query?preset=1d&search=users"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert "users" in data["items"][0]["query_signature"]


@pytest.mark.asyncio
async def test_query_analytics_exclude(
    auth_client: AsyncClient,
    db_session,
    test_server_and_database,
):
    _, database = test_server_and_database
    now = datetime.now(timezone.utc)
    base = now - timedelta(hours=1)

    rows = [
        NativeQueryMetric(
            collected_at=base + timedelta(minutes=1),
            database_id=database.id,
            pid=100,
            backend_start=base,
            user_name="user_a",
            application_name="app_1",
            state="active",
            query="SELECT * FROM users",
            query_hash="hash1",
            query_duration_ms=10.0,
        ),
        NativeQueryMetric(
            collected_at=base + timedelta(minutes=2),
            database_id=database.id,
            pid=200,
            backend_start=base,
            user_name="user_b",
            application_name="app_2",
            state="active",
            query="DELETE FROM logs",
            query_hash="hash2",
            query_duration_ms=20.0,
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()

    response = await auth_client.get(
        f"/v1/databases/{database.public_id}/analytics/query?preset=1d&exclude=delete"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert "users" in data["items"][0]["query_signature"]


@pytest.mark.asyncio
async def test_query_analytics_not_found(auth_client: AsyncClient):
    response = await auth_client.get(f"/v1/databases/{uuid.uuid4()}/analytics/query?preset=1d")
    assert response.status_code == 404
