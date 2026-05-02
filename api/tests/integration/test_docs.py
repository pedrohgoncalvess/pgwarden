import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient

from database.models.collector.server import Server
from database.models.metadata.database import Database
from database.models.metadata.table import Table
from database.models.metadata.column import ColumnModel
from database.models.metadata.index import Index
from database.models.doc.tag import Tag
from utils import encrypt


@pytest_asyncio.fixture
async def test_server(db_session):
    server = Server(
        name="Docs Test Server",
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


@pytest_asyncio.fixture
async def test_database(db_session, test_server):
    db = Database(
        server_id=test_server.id,
        db_name=encrypt("docs_test_db"),
        public_id=uuid.uuid4()
    )
    db_session.add(db)
    await db_session.commit()
    await db_session.refresh(db)
    return db


@pytest_asyncio.fixture
async def test_table(db_session, test_database):
    table = Table(
        oid=1001,
        database_id=test_database.id,
        schema_name="public",
        name="users",
        public_id=uuid.uuid4()
    )
    db_session.add(table)
    await db_session.commit()
    await db_session.refresh(table)
    return table


@pytest_asyncio.fixture
async def test_column(db_session, test_table):
    column = ColumnModel(
        table_id=test_table.id,
        name="email",
        data_type="text",
        ordinal_position=1,
        public_id=uuid.uuid4()
    )
    db_session.add(column)
    await db_session.commit()
    await db_session.refresh(column)
    return column


@pytest_asyncio.fixture
async def test_index(db_session, test_database, test_table):
    index = Index(
        database_id=test_database.id,
        table_id=test_table.id,
        oid=2001,
        name="idx_users_email",
        type="btree",
        definition="CREATE INDEX idx_users_email ON public.users USING btree (email)",
        public_id=uuid.uuid4()
    )
    db_session.add(index)
    await db_session.commit()
    await db_session.refresh(index)
    return index


@pytest_asyncio.fixture
async def test_tag(db_session, test_server):
    tag = Tag(
        server_id=test_server.id,
        name="PII",
        color="#FF0000",
        public_id=uuid.uuid4()
    )
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    return tag


# --- DATABASE DOC TESTS ---
@pytest.mark.asyncio
async def test_put_database_doc_success(auth_client: AsyncClient, test_database):
    payload = {"description": "This is a test database."}
    response = await auth_client.put(f"/v1/databases/{test_database.public_id}/doc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == payload["description"]

@pytest.mark.asyncio
async def test_get_database_doc_success(auth_client: AsyncClient, test_database):
    payload = {"description": "Database to test get."}
    await auth_client.put(f"/v1/databases/{test_database.public_id}/doc", json=payload)
    
    response = await auth_client.get(f"/v1/databases/{test_database.public_id}/doc")
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == payload["description"]

@pytest.mark.asyncio
async def test_attach_and_detach_database_tag(auth_client: AsyncClient, test_database, test_tag):
    # Setup doc first
    await auth_client.put(f"/v1/databases/{test_database.public_id}/doc", json={"description": "DB"})
    
    # Attach tag
    res_attach = await auth_client.post(f"/v1/databases/{test_database.public_id}/tags/{test_tag.public_id}")
    assert res_attach.status_code == 204
    
    # Detach tag
    res_detach = await auth_client.delete(f"/v1/databases/{test_database.public_id}/tags/{test_tag.public_id}")
    assert res_detach.status_code == 204


# --- SCHEMA DOC TESTS ---
@pytest.mark.asyncio
async def test_put_schema_doc_success(auth_client: AsyncClient, test_database):
    payload = {"description": "Public schema"}
    response = await auth_client.put(f"/v1/databases/{test_database.public_id}/schemas/public/doc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == payload["description"]

@pytest.mark.asyncio
async def test_get_schema_doc_success(auth_client: AsyncClient, test_database):
    payload = {"description": "Public schema for get"}
    await auth_client.put(f"/v1/databases/{test_database.public_id}/schemas/public/doc", json=payload)
    
    response = await auth_client.get(f"/v1/databases/{test_database.public_id}/schemas/public/doc")
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == payload["description"]

@pytest.mark.asyncio
async def test_attach_and_detach_schema_tag(auth_client: AsyncClient, test_database, test_tag):
    await auth_client.put(f"/v1/databases/{test_database.public_id}/schemas/public/doc", json={"description": "SC"})
    
    res_attach = await auth_client.post(f"/v1/databases/{test_database.public_id}/schemas/public/tags/{test_tag.public_id}")
    assert res_attach.status_code == 204
    
    res_detach = await auth_client.delete(f"/v1/databases/{test_database.public_id}/schemas/public/tags/{test_tag.public_id}")
    assert res_detach.status_code == 204


# --- TABLE DOC TESTS ---
@pytest.mark.asyncio
async def test_put_table_doc_success(auth_client: AsyncClient, test_database, test_table):
    payload = {"description": "Users table"}
    response = await auth_client.put(f"/v1/databases/{test_database.public_id}/tables/{test_table.public_id}/doc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == payload["description"]

@pytest.mark.asyncio
async def test_get_table_doc_success(auth_client: AsyncClient, test_database, test_table):
    payload = {"description": "Table for get"}
    await auth_client.put(f"/v1/databases/{test_database.public_id}/tables/{test_table.public_id}/doc", json=payload)
    
    response = await auth_client.get(f"/v1/databases/{test_database.public_id}/tables/{test_table.public_id}/doc")
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == payload["description"]

@pytest.mark.asyncio
async def test_attach_and_detach_table_tag(auth_client: AsyncClient, test_database, test_table, test_tag):
    await auth_client.put(f"/v1/databases/{test_database.public_id}/tables/{test_table.public_id}/doc", json={"description": "TBL"})
    
    res_attach = await auth_client.post(f"/v1/databases/{test_database.public_id}/tables/{test_table.public_id}/tags/{test_tag.public_id}")
    assert res_attach.status_code == 204
    
    res_detach = await auth_client.delete(f"/v1/databases/{test_database.public_id}/tables/{test_table.public_id}/tags/{test_tag.public_id}")
    assert res_detach.status_code == 204


# --- COLUMN DOC TESTS ---
@pytest.mark.asyncio
async def test_put_column_doc_success(auth_client: AsyncClient, test_database, test_column):
    payload = {"description": "Email column"}
    response = await auth_client.put(f"/v1/databases/{test_database.public_id}/columns/{test_column.public_id}/doc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == payload["description"]

@pytest.mark.asyncio
async def test_get_column_doc_success(auth_client: AsyncClient, test_database, test_column):
    payload = {"description": "Column for get"}
    await auth_client.put(f"/v1/databases/{test_database.public_id}/columns/{test_column.public_id}/doc", json=payload)
    
    response = await auth_client.get(f"/v1/databases/{test_database.public_id}/columns/{test_column.public_id}/doc")
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == payload["description"]

@pytest.mark.asyncio
async def test_attach_and_detach_column_tag(auth_client: AsyncClient, test_database, test_column, test_tag):
    await auth_client.put(f"/v1/databases/{test_database.public_id}/columns/{test_column.public_id}/doc", json={"description": "COL"})
    
    res_attach = await auth_client.post(f"/v1/databases/{test_database.public_id}/columns/{test_column.public_id}/tags/{test_tag.public_id}")
    assert res_attach.status_code == 204
    
    res_detach = await auth_client.delete(f"/v1/databases/{test_database.public_id}/columns/{test_column.public_id}/tags/{test_tag.public_id}")
    assert res_detach.status_code == 204


# --- INDEX DOC TESTS ---
@pytest.mark.asyncio
async def test_put_index_doc_success(auth_client: AsyncClient, test_database, test_index):
    payload = {"description": "Index for user emails"}
    response = await auth_client.put(f"/v1/databases/{test_database.public_id}/indexes/{test_index.public_id}/doc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == payload["description"]

@pytest.mark.asyncio
async def test_get_index_doc_success(auth_client: AsyncClient, test_database, test_index):
    payload = {"description": "Index for get"}
    await auth_client.put(f"/v1/databases/{test_database.public_id}/indexes/{test_index.public_id}/doc", json=payload)
    
    response = await auth_client.get(f"/v1/databases/{test_database.public_id}/indexes/{test_index.public_id}/doc")
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == payload["description"]

@pytest.mark.asyncio
async def test_attach_and_detach_index_tag(auth_client: AsyncClient, test_database, test_index, test_tag):
    await auth_client.put(f"/v1/databases/{test_database.public_id}/indexes/{test_index.public_id}/doc", json={"description": "IDX"})
    
    res_attach = await auth_client.post(f"/v1/databases/{test_database.public_id}/indexes/{test_index.public_id}/tags/{test_tag.public_id}")
    assert res_attach.status_code == 204
    
    res_detach = await auth_client.delete(f"/v1/databases/{test_database.public_id}/indexes/{test_index.public_id}/tags/{test_tag.public_id}")
    assert res_detach.status_code == 204
