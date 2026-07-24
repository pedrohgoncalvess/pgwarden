import pytest
import pytest_asyncio
from httpx import AsyncClient

from database.models.notifier.rule import NotifierRule
from database.models.notifier.rule_database import RuleDatabase


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
