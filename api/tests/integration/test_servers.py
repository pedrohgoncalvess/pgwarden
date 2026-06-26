import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_create_server_success(auth_client: AsyncClient):
    """Tests the successful registration of a new PostgreSQL server."""
    server_data = {
        "name": "Production DB",
        "host": "localhost",
        "port": "5432",
        "username": "postgres",
        "password": "password",
        "ssl_mode": "prefer",
        "ignore_patterns": ["pg_%"],
        "ignore_tables": ["temp_table"],
        "include_tables": ["users", "orders"]
    }
    
    response = await auth_client.post("/v1/servers/", json=server_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Server created successfully"
    assert "id" in data

@pytest.mark.asyncio
async def test_list_servers(auth_client: AsyncClient, db_session):
    """Tests the retrieval of all registered servers for an authenticated user."""
    from database.models.collector.server import Server
    
    server = Server(
        name="Test Server",
        host="encrypted-host",
        port="encrypted-port",
        username="encrypted-user",
        password="encrypted-pass",
        public_id=uuid.uuid4()
    )
    db_session.add(server)
    await db_session.commit()
    
    response = await auth_client.get("/v1/servers/")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(s["name"] == "Test Server" for s in data)

@pytest.mark.asyncio
async def test_test_connection_success(auth_client: AsyncClient):
    """Tests the connection test endpoint with mocked successful response."""
    connection_data = {
        "name": "Test Server",
        "host": "localhost",
        "port": "5432",
        "username": "postgres",
        "password": "password",
        "ssl_mode": "disable"
    }
    
    with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect:
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = "PostgreSQL 17.0"
        mock_connect.return_value = mock_conn
        
        response = await auth_client.post("/v1/servers/test-connection", json=connection_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "PostgreSQL 17.0" in data["version"]

@pytest.mark.asyncio
async def test_test_connection_invalid_port(auth_client: AsyncClient):
    """Tests the connection test endpoint with an invalid port format."""
    connection_data = {
        "name": "Test Server",
        "host": "localhost",
        "port": "not-a-number",
        "username": "postgres",
        "password": "password",
        "ssl_mode": "disable"
    }
    
    response = await auth_client.post("/v1/servers/test-connection", json=connection_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert data["code"] == "Invalid port"

@pytest.mark.asyncio
async def test_create_server_unauthorized(client: AsyncClient):
    """Tests that server registration requires authentication."""
    response = await client.post("/v1/servers/", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_process_history_not_found(auth_client: AsyncClient):
    """Tests that process history returns 404 for a non-existent server."""
    response = await auth_client.get("/v1/servers/non-existent-id/configs/processes/history")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_process_history_success(auth_client: AsyncClient, db_session):
    """Tests retrieving process history for a server's collectors."""
    from database.models.collector.server import Server
    from database.models.collector.config_server import ConfigServer
    from database.models.collector.run import Run

    server = Server(
        name="Process Test Server",
        host="encrypted-host",
        port="encrypted-port",
        username="encrypted-user",
        password="encrypted-pass",
    )
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)

    config = ConfigServer(server_id=server.id, name="cpu_collector", interval=60, is_paused=False)
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)

    run = Run(config_server_id=config.id, status="success", finished_at=datetime.now(timezone.utc))
    db_session.add(run)
    await db_session.commit()

    response = await auth_client.get(f"/v1/servers/{server.public_id}/configs/processes/history")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "success"
    assert data[0]["name"] == "cpu_collector"


@pytest.mark.asyncio
async def test_patch_process_pause_resume(auth_client: AsyncClient, db_session):
    """Tests pausing and resuming a server collector process."""
    from database.models.collector.server import Server
    from database.models.collector.config_server import ConfigServer

    server = Server(
        name="Control Test Server",
        host="encrypted-host",
        port="encrypted-port",
        username="encrypted-user",
        password="encrypted-pass",
    )
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)

    config = ConfigServer(server_id=server.id, name="ram_collector", interval=60, is_paused=False)
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)

    response = await auth_client.patch(
        f"/v1/servers/{server.public_id}/configs/processes/{config.id}?process_type=server",
        json={"action": "pause"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_paused"] is True
    assert data["status"] == "paused"

    response = await auth_client.patch(
        f"/v1/servers/{server.public_id}/configs/processes/{config.id}?process_type=server",
        json={"action": "resume"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_paused"] is False


@pytest.mark.asyncio
async def test_patch_process_delete(auth_client: AsyncClient, db_session):
    """Tests deleting a server collector process."""
    from database.models.collector.server import Server
    from database.models.collector.config_server import ConfigServer

    server = Server(
        name="Delete Test Server",
        host="encrypted-host",
        port="encrypted-port",
        username="encrypted-user",
        password="encrypted-pass",
    )
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)

    config = ConfigServer(server_id=server.id, name="disk_collector", interval=60, is_paused=False)
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)

    response = await auth_client.patch(
        f"/v1/servers/{server.public_id}/configs/processes/{config.id}?process_type=server",
        json={"action": "delete"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "delete"
    assert data["status"] == "deleted"


@pytest.mark.asyncio
async def test_stream_processes_not_found(auth_client: AsyncClient):
    """Tests that the process SSE stream returns 404 for a non-existent server."""
    response = await auth_client.get("/v1/servers/non-existent-id/configs/processes/stream")
    assert response.status_code == 404
