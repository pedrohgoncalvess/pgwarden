import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from database.models.collector import Server
from database.models.metadata import (
    Database, Table, ColumnModel, Index, IndexColumn,
    TableHistory, ColumnHistory, IndexHistory
)
from utils import encrypt


@pytest_asyncio.fixture
async def full_schema_setup(db_session):
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
    db = full_schema_setup
    
    response = await auth_client.get(f"/v1/databases/{db.public_id}/schemas")
    
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
    random_id = uuid.uuid4()
    response = await auth_client.get(f"/v1/databases/{random_id}/schemas")
    
    assert response.status_code == 404
    assert response.json()["message"] == f"Database {random_id} not found"

@pytest.mark.asyncio
async def test_get_schema_unauthorized(client: AsyncClient):
    random_id = uuid.uuid4()
    response = await client.get(f"/v1/databases/{random_id}/schemas")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_schema_history_success(auth_client: AsyncClient, db_session, full_schema_setup):
    """Tests successful retrieval of the schema change history."""
    db = full_schema_setup

    result = await db_session.execute(select(Table).where(Table.database_id == db.id))
    table = result.scalar_one()

    result = await db_session.execute(select(ColumnModel).where(ColumnModel.table_id == table.id))
    column = result.scalar_one()

    result = await db_session.execute(select(Index).where(Index.table_id == table.id))
    index = result.scalar_one()

    now = datetime.now(timezone.utc)

    table_history = TableHistory(
        table_id=table.id,
        table_oid=table.oid,
        schema_name=table.schema_name,
        name="old_users",
        description=table.description,
        changed_at=now,
        changed_by=None,
    )
    db_session.add(table_history)

    column_history = ColumnHistory(
        column_id=column.id,
        table_id=table.id,
        name="old_id",
        description=column.description,
        data_type=column.data_type,
        is_nullable=column.is_nullable,
        default_value=column.default_value,
        is_unique=column.is_unique,
        ordinal_position=column.ordinal_position,
        fk_table_id=column.fk_table_id,
        fk_column_id=column.fk_column_id,
        changed_at=now,
        changed_by=None,
    )
    db_session.add(column_history)

    index_history = IndexHistory(
        index_id=index.id,
        table_id=table.id,
        index_oid=index.oid,
        name="old_users_pkey",
        type=index.type,
        definition=index.definition,
        is_unique=index.is_unique,
        is_primary=index.is_primary,
        changed_at=now,
        changed_by=None,
    )
    db_session.add(index_history)

    removed_column = ColumnModel(
        table_id=table.id,
        name="email",
        data_type="text",
        is_nullable=True,
        ordinal_position=2,
        deleted_at=now,
        public_id=uuid.uuid4(),
    )
    db_session.add(removed_column)

    await db_session.commit()

    response = await auth_client.get(f"/v1/databases/{db.public_id}/schemas/history?limit=100&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 100
    assert data["offset"] == 0
    assert data["total"] >= 4

    actions = {item["action"] for item in data["items"]}
    assert "added" not in actions
    assert "altered" in actions
    assert "removed" in actions

    types = {item["type"] for item in data["items"]}
    assert "table" in types
    assert "column" in types
    assert "index" in types

    altered_items = [item for item in data["items"] if item["action"] == "altered"]
    assert any(item["type"] == "table" and "old_users" in item["details"] for item in altered_items)
    assert any(item["type"] == "column" and "old_id" in item["details"] for item in altered_items)
    assert any(item["type"] == "index" and "old_users_pkey" in item["details"] for item in altered_items)


@pytest.mark.asyncio
async def test_get_schema_history_not_found(auth_client: AsyncClient):
    random_id = uuid.uuid4()
    response = await auth_client.get(f"/v1/databases/{random_id}/schemas/history")

    assert response.status_code == 404
    assert response.json()["message"] == f"Database {random_id} not found"


@pytest.mark.asyncio
async def test_get_schema_history_unauthorized(client: AsyncClient):
    random_id = uuid.uuid4()
    response = await client.get(f"/v1/databases/{random_id}/schemas/history")
    assert response.status_code == 401
