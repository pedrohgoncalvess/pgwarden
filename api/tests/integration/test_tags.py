import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from database.models.collector.server import Server


@pytest_asyncio.fixture
async def tag_server(db_session):
    server = Server(
        name="Tag API Server",
        host="localhost",
        port="5432",
        username="postgres",
        password="password",
        public_id=uuid.uuid4(),
    )
    db_session.add(server)
    await db_session.commit()
    return server


@pytest.mark.asyncio
async def test_tag_crud_lifecycle(auth_client: AsyncClient, tag_server):
    create_payload = {
        "server_id": str(tag_server.public_id),
        "name": "Critical",
        "description": "Requires immediate attention",
        "color": "#DC2626",
        "type": "severity",
    }
    created = await auth_client.post("/v1/tags/", json=create_payload)
    assert created.status_code == 201
    tag = created.json()
    assert tag["name"] == "Critical"
    assert tag["color"] == "#DC2626"

    listed = await auth_client.get(f"/v1/tags/?server_id={tag_server.public_id}")
    assert listed.status_code == 200
    assert any(item["id"] == tag["id"] for item in listed.json())

    updated = await auth_client.patch(
        f"/v1/tags/{tag['id']}",
        json={"name": "Urgent", "color": "#B91C1C"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Urgent"
    assert updated.json()["description"] == create_payload["description"]

    deleted = await auth_client.delete(f"/v1/tags/{tag['id']}")
    assert deleted.status_code == 204

    listed_after_delete = await auth_client.get(f"/v1/tags/?server_id={tag_server.public_id}")
    assert listed_after_delete.status_code == 200
    assert all(item["id"] != tag["id"] for item in listed_after_delete.json())


@pytest.mark.asyncio
async def test_tag_create_rejects_duplicate_name(auth_client: AsyncClient, tag_server):
    payload = {"server_id": str(tag_server.public_id), "name": "PII"}
    assert (await auth_client.post("/v1/tags/", json=payload)).status_code == 201
    duplicate = await auth_client.post("/v1/tags/", json=payload)
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_tag_operations_return_not_found_for_unknown_tag(auth_client: AsyncClient):
    tag_id = uuid.uuid4()
    assert (await auth_client.patch(f"/v1/tags/{tag_id}", json={"name": "Missing"})).status_code == 404
    assert (await auth_client.delete(f"/v1/tags/{tag_id}")).status_code == 404
