import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from database.models.collector import Server
from database.models.metadata import Database, Table, ColumnModel, Index, IndexColumn
from utils import encrypt


@pytest_asyncio.fixture
async def full_schema_setup(db_session):
    """Creates a complete database schema hierarchy for testing the schema retrieval endpoint."""
    server = Server(
        name="Schema Test Server",
        host="localhost",
        port="5432",
        username="postgres",
        password="password",
        public_id=uuid.uuid4()
    )
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)

    db = Database(
        server_id=server.id,
        db_name=encrypt("schema_test_db"),
        public_id=uuid.uuid4()
    )
    db_session.add(db)
    await db_session.commit()
    await db_session.refresh(db)

    table = Table(
        database_id=db.id,
        schema_name="public",
        name="users",
        description="User table",
        oid=12345,
        public_id=uuid.uuid4()
    )
    db_session.add(table)
    await db_session.commit()
    await db_session.refresh(table)

    column = ColumnModel(
        table_id=table.id,
        name="id",
        data_type="integer",
        is_nullable=False,
        ordinal_position=1,
        public_id=uuid.uuid4()
    )
    db_session.add(column)
    await db_session.commit()
    await db_session.refresh(column)

    index = Index(
        database_id=db.id,
        table_id=table.id,
        name="users_pkey",
        type="btree",
        definition="CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id)",
        is_unique=True,
        is_primary=True,
        oid=54321,
        public_id=uuid.uuid4()
    )
    db_session.add(index)
    await db_session.commit()
    await db_session.refresh(index)

    idx_col = IndexColumn(
        index_id=index.id,
        column_id=column.id,
        ordinal_position=1
    )
    db_session.add(idx_col)
    await db_session.commit()

    return db

@pytest.mark.asyncio
async def test_get_schema_success(auth_client: AsyncClient, full_schema_setup):
    """Tests successful retrieval of the full database schema metadata."""
    db = full_schema_setup
    
    response = await auth_client.get(f"/v1/schemas/{db.public_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(db.public_id)
    assert len(data["tables"]) == 1
    
    table = data["tables"][0]
    assert table["name"] == "users"
    assert len(table["columns"]) == 1
    assert table["columns"][0]["name"] == "id"
    assert len(table["indexes"]) == 1
    assert table["indexes"][0]["name"] == "users_pkey"

@pytest.mark.asyncio
async def test_get_schema_not_found(auth_client: AsyncClient):
    """Tests schema retrieval failure when the database ID does not exist."""
    random_id = uuid.uuid4()
    response = await auth_client.get(f"/v1/schemas/{random_id}")
    
    assert response.status_code == 404
    assert response.json()["message"] == f"Database {random_id} not found"

@pytest.mark.asyncio
async def test_get_schema_unauthorized(client: AsyncClient):
    """Tests that retrieving schema metadata requires authentication."""
    random_id = uuid.uuid4()
    response = await client.get(f"/v1/schemas/{random_id}")
    assert response.status_code == 401
