import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from database.models.collector.server import Server
from database.models.collector.config_database import ConfigDatabase
from database.models.metadata.database import Database
from utils import encrypt


@pytest_asyncio.fixture
async def test_server_with_run(db_session):
    """Creates a test server, database and an active database config run."""
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
        db_name=encrypt("run_test_db"),
        public_id=uuid.uuid4(),
    )
    db_session.add(database)
    await db_session.commit()
    await db_session.refresh(database)

    config = ConfigDatabase(
        database_id=database.id,
        name="test_collector",
        interval=60.0,
        is_paused=False,
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)

    return server, database, config


@pytest.mark.asyncio
async def test_force_run_creates_command(
    auth_client: AsyncClient,
    db_session,
    test_server_with_run,
):
    _, database, config = test_server_with_run

    response = await auth_client.patch(
        f"/v1/databases/{database.public_id}/runs/{config.id}?run_type=database",
        json={"action": "force_run"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "force_run"
    assert data["id"] == config.id


@pytest.mark.asyncio
async def test_force_run_paused_fails(
    auth_client: AsyncClient,
    db_session,
    test_server_with_run,
):
    _, database, config = test_server_with_run
    config.is_paused = True
    await db_session.commit()

    response = await auth_client.patch(
        f"/v1/databases/{database.public_id}/runs/{config.id}?run_type=database",
        json={"action": "force_run"},
    )
    assert response.status_code == 400
