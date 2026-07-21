import json
from datetime import datetime

from notifier.channels.base import Alert
from notifier.services.notifications import build_params, path_for


class FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class FakeSession:
    def __init__(self, row):
        self._row = row

    async def execute(self, query, params):
        return FakeResult(self._row)


def make_alert(scope: str, entity_id: int | None, window: float = 5.0) -> Alert:
    return Alert(
        rule="hit_rate",
        severity="critical",
        entity="users_email_idx",
        message="Hit rate do índice abaixo do threshold",
        value=0.75,
        threshold=0.8,
        scope=scope,
        entity_id=entity_id,
        rule_name="default",
        window_minutes=window,
    )


def test_path_for_all_scopes():
    assert path_for("server", 7, None) == "/servers"
    assert path_for("server", None, None) == "/servers"
    assert path_for("database", 12, 12) == "/overview/12"
    assert path_for("table", 55, 12) == "/analytics/12/data"
    assert path_for("index", 99, 12) == "/analytics/12/index"
    assert path_for("table", 55, None) is None


async def test_build_params_index_scope():
    alert = make_alert("index", 99, window=10.0)
    params = await build_params(FakeSession((12,)), alert)

    assert params["path"] == "/analytics/12/index"
    assert params["scope"] == "index"
    assert params["type"] == "hit_rate"
    assert params["rule"] == "default"
    assert params["entity"] == "users_email_idx"
    assert params["entity_id"] == 99
    assert params["database_id"] == 12
    assert params["severity"] == "critical"
    assert params["value"] == 0.75
    assert params["threshold"] == 0.8
    start = datetime.fromisoformat(params["from"])
    end = datetime.fromisoformat(params["to"])
    assert (end - start).total_seconds() == 600


async def test_build_params_database_scope_uses_entity_id():
    alert = make_alert("database", 12)
    params = await build_params(FakeSession(None), alert)

    assert params["path"] == "/overview/12"
    assert params["database_id"] == 12


async def test_build_params_table_scope_resolves_database():
    alert = make_alert("table", 55)
    params = await build_params(FakeSession((12,)), alert)

    assert params["path"] == "/analytics/12/data"
    assert params["database_id"] == 12


async def test_build_params_global_target_has_no_path():
    alert = make_alert("index", None)
    params = await build_params(FakeSession(None), alert)

    assert params["path"] is None
    assert params["entity_id"] is None
    assert params["database_id"] is None


def test_params_are_json_serializable():
    params = {
        "path": "/analytics/12/index",
        "value": 0.75,
    }
    assert json.loads(json.dumps(params)) == params
