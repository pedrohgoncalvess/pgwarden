import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from database.models.collector.server import Server
from database.models.metadata.database import Database
from utils import encrypt


@pytest_asyncio.fixture
async def test_server(db_session):
    """Creates a test server in the collector schema for database linking."""
    server = Server(
        name="Test Server",
        host="localhost",
        port="5432",
        username="postgres",
        password="password",
        public_id=uuid.uuid4()
    )
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    return server

@pytest.mark.asyncio
async def test_create_database_success(auth_client: AsyncClient, test_server):
    """Tests the successful registration of a new monitored database."""
    db_data = {
        "server_id": str(test_server.public_id),
        "db_name": "new_monitored_db"
    }
    
    response = await auth_client.post("/v1/databases/", json=db_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Database created successfully"
    assert "id" in data

@pytest.mark.asyncio
async def test_create_database_server_not_found(auth_client: AsyncClient):
    """Tests database registration failure when the parent server ID is invalid."""
    db_data = {
        "server_id": str(uuid.uuid4()),
        "db_name": "orphaned_db"
    }
    
    response = await auth_client.post("/v1/databases/", json=db_data)
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Server not found"

@pytest.mark.asyncio
async def test_list_databases(auth_client: AsyncClient, db_session, test_server):
    """Tests the retrieval of all registered databases for an authenticated user."""
    db = Database(
        server_id=test_server.id,
        db_name=encrypt("existing_db"),
        public_id=uuid.uuid4()
    )
    db_session.add(db)
    await db_session.commit()
    
    response = await auth_client.get("/v1/databases/")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(d["name"] == "existing_db" for d in data)

@pytest.mark.asyncio
async def test_list_databases_unauthorized(client: AsyncClient):
    """Tests that listing databases requires authentication."""
    response = await client.get("/v1/databases/")
    assert response.status_code == 401
