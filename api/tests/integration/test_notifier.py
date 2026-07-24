import os

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import AsyncClient

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from database.models.notifier.rule import NotifierRule
from database.models.notifier.rule_database import RuleDatabase
from database.models.notifier.channel import NotifierChannel


@pytest_asyncio.fixture
async def test_rule(db_session):
    rule = NotifierRule(
        name="test_database_growth",
        interval_seconds=120,
        cooldown_seconds=900,
        window_minutes=10,
        enabled=True,
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    threshold = RuleDatabase(
        rule_id=rule.id,
        database_id=None,
        type="growth_percent",
        warning=10.0,
        critical=20.0,
        direction="above",
    )
    db_session.add(threshold)
    await db_session.commit()
    await db_session.refresh(threshold)

    return rule, threshold


@pytest.mark.asyncio
async def test_list_rules(auth_client: AsyncClient, test_rule):
    response = await auth_client.get("/v1/notifier/rules")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    rule = next(r for r in data if r["name"] == "test_database_growth")
    assert rule["interval_seconds"] == 120
    assert len(rule["thresholds"]) == 1
    assert rule["thresholds"][0]["scope"] == "database"
    assert rule["thresholds"][0]["type"] == "growth_percent"


@pytest.mark.asyncio
async def test_get_rule(auth_client: AsyncClient, test_rule):
    rule, _ = test_rule
    response = await auth_client.get(f"/v1/notifier/rules/{rule.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test_database_growth"
    assert len(data["thresholds"]) == 1


@pytest.mark.asyncio
async def test_get_rule_not_found(auth_client: AsyncClient):
    response = await auth_client.get("/v1/notifier/rules/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_rule(auth_client: AsyncClient, test_rule):
    rule, _ = test_rule
    response = await auth_client.patch(
        f"/v1/notifier/rules/{rule.id}",
        json={"interval_seconds": 300, "enabled": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["interval_seconds"] == 300
    assert data["enabled"] is False


@pytest.mark.asyncio
async def test_patch_rule_no_fields(auth_client: AsyncClient, test_rule):
    rule, _ = test_rule
    response = await auth_client.patch(
        f"/v1/notifier/rules/{rule.id}",
        json={},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_threshold(auth_client: AsyncClient, test_rule):
    rule, threshold = test_rule
    response = await auth_client.get(
        f"/v1/notifier/rules/{rule.id}/thresholds/database/{threshold.id}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "database"
    assert data["warning"] == 10.0
    assert data["critical"] == 20.0


@pytest.mark.asyncio
async def test_get_threshold_invalid_scope(auth_client: AsyncClient, test_rule):
    rule, threshold = test_rule
    response = await auth_client.get(
        f"/v1/notifier/rules/{rule.id}/thresholds/invalid/{threshold.id}"
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_patch_threshold(auth_client: AsyncClient, test_rule):
    rule, threshold = test_rule
    response = await auth_client.patch(
        f"/v1/notifier/rules/{rule.id}/thresholds/database/{threshold.id}",
        json={"warning": 15.0, "direction": "below"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["warning"] == 15.0
    assert data["critical"] == 20.0
    assert data["direction"] == "below"


@pytest.mark.asyncio
async def test_patch_threshold_invalid_direction(auth_client: AsyncClient, test_rule):
    rule, threshold = test_rule
    response = await auth_client.patch(
        f"/v1/notifier/rules/{rule.id}/thresholds/database/{threshold.id}",
        json={"direction": "sideways"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_threshold(auth_client: AsyncClient, test_rule):
    rule, threshold = test_rule
    response = await auth_client.delete(
        f"/v1/notifier/rules/{rule.id}/thresholds/database/{threshold.id}"
    )
    assert response.status_code == 204

    response = await auth_client.get(
        f"/v1/notifier/rules/{rule.id}/thresholds/database/{threshold.id}"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_rules_unauthorized(client: AsyncClient):
    response = await client.get("/v1/notifier/rules")
    assert response.status_code == 401


@pytest_asyncio.fixture
async def test_channel(db_session):
    channel = NotifierChannel(
        name="slack",
        enabled=False,
        credentials=None,
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return channel


@pytest.mark.asyncio
async def test_list_rule_types(auth_client: AsyncClient):
    response = await auth_client.get("/v1/notifier/rule-types")
    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"server", "database", "table", "index"}
    assert "cpu_percent" in data["server"]
    assert "hit_rate" in data["index"]


@pytest.mark.asyncio
async def test_create_rule(auth_client: AsyncClient):
    response = await auth_client.post(
        "/v1/notifier/rules",
        json={"name": "new_rule", "interval_seconds": 300},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "new_rule"
    assert data["interval_seconds"] == 300
    assert data["cooldown_seconds"] == 1800
    assert data["thresholds"] == []


@pytest.mark.asyncio
async def test_create_rule_duplicate(auth_client: AsyncClient, test_rule):
    response = await auth_client.post(
        "/v1/notifier/rules",
        json={"name": "test_database_growth"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_threshold(auth_client: AsyncClient, test_rule):
    rule, _ = test_rule
    response = await auth_client.post(
        f"/v1/notifier/rules/{rule.id}/thresholds",
        json={
            "scope": "server",
            "type": "cpu_percent",
            "warning": 80,
            "critical": 95,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["scope"] == "server"
    assert data["type"] == "cpu_percent"
    assert data["direction"] == "above"
    assert data["entity_id"] is None


@pytest.mark.asyncio
async def test_create_threshold_invalid_scope(auth_client: AsyncClient, test_rule):
    rule, _ = test_rule
    response = await auth_client.post(
        f"/v1/notifier/rules/{rule.id}/thresholds",
        json={"scope": "invalid", "type": "cpu_percent", "warning": 1, "critical": 2},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_threshold_invalid_type(auth_client: AsyncClient, test_rule):
    rule, _ = test_rule
    response = await auth_client.post(
        f"/v1/notifier/rules/{rule.id}/thresholds",
        json={"scope": "server", "type": "hit_rate", "warning": 1, "critical": 2},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_threshold_rule_not_found(auth_client: AsyncClient):
    response = await auth_client.post(
        "/v1/notifier/rules/999999/thresholds",
        json={"scope": "server", "type": "cpu_percent", "warning": 1, "critical": 2},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_threshold_duplicate(auth_client: AsyncClient, test_rule):
    rule, _ = test_rule
    response = await auth_client.post(
        f"/v1/notifier/rules/{rule.id}/thresholds",
        json={
            "scope": "database",
            "type": "growth_percent",
            "warning": 15,
            "critical": 30,
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_channels(auth_client: AsyncClient, test_channel):
    response = await auth_client.get("/v1/notifier/channels")
    assert response.status_code == 200
    data = response.json()
    channel = next(c for c in data if c["name"] == "slack")
    assert channel["enabled"] is False
    assert channel["has_credentials"] is False
    assert "credentials" not in channel


@pytest.mark.asyncio
async def test_patch_channel(auth_client: AsyncClient, test_channel):
    response = await auth_client.patch(
        f"/v1/notifier/channels/{test_channel.id}",
        json={"enabled": True, "credentials": {"webhook_url": "https://hooks.slack.com/x"}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["has_credentials"] is True


@pytest.mark.asyncio
async def test_patch_channel_no_fields(auth_client: AsyncClient, test_channel):
    response = await auth_client.patch(
        f"/v1/notifier/channels/{test_channel.id}",
        json={},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_patch_channel_not_found(auth_client: AsyncClient):
    response = await auth_client.patch(
        "/v1/notifier/channels/999999",
        json={"enabled": True},
    )
    assert response.status_code == 404
