import uuid

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
