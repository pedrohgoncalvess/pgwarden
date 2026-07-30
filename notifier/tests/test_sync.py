"""Tests for notifier.config.sync — DB synchronization of rules and channels.

Uses a fake session that records executed statements and returns canned
responses matched by query substring, so the real SQL never hits a database.
"""

from unittest.mock import patch

import pytest

from notifier.config import sync as sync_module
from notifier.config.load import ChannelYamlConfig, NotifierYamlConfig, RuleYamlConfig, TargetYamlConfig


class FakeResult:
    def __init__(self, *, first=None, scalar=None, rows=None):
        self._first = first
        self._scalar = scalar
        self._rows = rows or []

    def first(self):
        return self._first

    def scalar_one(self):
        return self._scalar

    def fetchall(self):
        return self._rows


class FakeSession:
    def __init__(self):
        self.executed = []
        self.committed = False
        self._responders = []

    def on(self, substring, result):
        self._responders.append((substring, result))
        return self

    def _result_for(self, query_text):
        for substring, result in self._responders:
            if substring in query_text:
                return result() if callable(result) else result
        return FakeResult()

    async def execute(self, query, params=None):
        query_text = str(query)
        self.executed.append((query_text, params))
        return self._result_for(query_text)

    async def commit(self):
        self.committed = True


def _statements(session):
    return [q for q, _ in session.executed]


def _make_rule(*targets, name="r1"):
    return RuleYamlConfig(
        name=name, interval=30, cooldown=600, window_minutes=10, enabled=True, targets=list(targets),
    )


async def test_insert_rule_returns_id_and_passes_params():
    session = FakeSession().on("RETURNING id", FakeResult(scalar=42))

    rule_id = await sync_module._insert_rule(session, "default", 60, 1800, 5, True)

    assert rule_id == 42
    _, params = session.executed[0]
    assert params == {"name": "default", "interval": 60, "cooldown": 1800, "window": 5, "enabled": True}



async def test_seed_default_rule_skips_when_rule_exists():
    session = FakeSession().on("notifier.rule LIMIT 1", FakeResult(first=(1,)))

    await sync_module._seed_default_rule(session)

    assert len(session.executed) == 1


async def test_seed_default_rule_inserts_rule_and_all_scope_types():
    session = FakeSession()
    session.on("notifier.rule LIMIT 1", FakeResult(first=None))
    session.on("INSERT INTO notifier.rule", FakeResult(scalar=7))

    await sync_module._seed_default_rule(session)

    statements = _statements(session)
    expected_inserts = 1 + len(sync_module.RULE_TYPES)
    assert len(statements) == 1 + expected_inserts

    for table, _ in sync_module._SCOPE_TABLE.values():
        assert any(f"INSERT INTO {table}" in stmt for stmt in statements)

    for stmt, params in session.executed:
        if "INSERT INTO notifier.rule_" in stmt:
            assert params["rule_id"] == 7


async def test_upsert_rule_with_no_targets_deletes_from_all_scope_tables():
    session = FakeSession().on("RETURNING id", FakeResult(scalar=100))

    await sync_module._upsert_rule(session, _make_rule())

    statements = _statements(session)
    assert len(statements) == 5
    for table, _ in sync_module._SCOPE_TABLE.values():
        assert any(f"DELETE FROM {table}" in stmt for stmt in statements)


async def test_upsert_rule_inserts_one_row_per_resolved_entity(monkeypatch):
    target = TargetYamlConfig(
        scope="server", type="cpu_percent",
        names=[{"server": "srv1"}, {"server": "srv2"}], filters={},
        warning=80.0, critical=90.0, direction="above",
    )
    session = FakeSession().on("RETURNING id", FakeResult(scalar=100))

    async def fake_resolve_name(_session, scope, name):
        return {"srv1": 11, "srv2": 22}.get(name.get("server"))

    monkeypatch.setattr(sync_module, "_resolve_name", fake_resolve_name)

    await sync_module._upsert_rule(session, _make_rule(target))

    inserts = [
        (stmt, params) for stmt, params in session.executed
        if "INSERT INTO notifier.rule_server" in stmt
    ]
    assert len(inserts) == 2
    assert sorted(params["entity_id"] for _, params in inserts) == [11, 22]
    for _, params in inserts:
        assert params["type"] == "cpu_percent"
        assert params["warning"] == 80.0


async def test_upsert_rule_skips_target_when_no_entity_resolved(monkeypatch):
    target = TargetYamlConfig(
        scope="server", type="cpu_percent",
        names=[{"server": "ghost"}], filters={},
        warning=80.0, critical=90.0, direction="above",
    )
    session = FakeSession().on("RETURNING id", FakeResult(scalar=100))

    async def fake_resolve_name(*args, **kwargs):
        return None

    monkeypatch.setattr(sync_module, "_resolve_name", fake_resolve_name)

    await sync_module._upsert_rule(session, _make_rule(target))

    assert not any("INSERT INTO notifier.rule_server" in stmt for stmt, _ in session.executed)



async def test_resolve_entities_names_path_dedupes(monkeypatch):
    target = TargetYamlConfig(
        scope="database", type="cache_hit_ratio",
        names=[{"database": "a"}, {"database": "b"}, {"database": "a"}], filters={},
        warning=0.95, critical=0.90, direction="below",
    )

    async def fake_resolve_name(_session, scope, name):
        return {"a": 1, "b": 2}.get(name.get("database"))

    monkeypatch.setattr(sync_module, "_resolve_name", fake_resolve_name)

    ids = await sync_module._resolve_entities(FakeSession(), target, "rule")
    assert ids == [1, 2, 1]


async def test_resolve_entities_returns_none_when_no_names_no_filters():
    target = TargetYamlConfig(
        scope="server", type="cpu_percent", names=[], filters={},
        warning=80.0, critical=90.0, direction="above",
    )
    ids = await sync_module._resolve_entities(FakeSession(), target, "rule")
    assert ids == [None]


async def test_resolve_entities_table_filters_query():
    target = TargetYamlConfig(
        scope="table", type="dead_tuple_ratio", names=[],
        filters={"database": "app_db", "schemas": ["public"], "table_regex": "^fact_"},
        warning=0.2, critical=0.5, direction="above",
    )
    session = FakeSession().on("metadata.table t", FakeResult(rows=[(10,), (20,)]))

    ids = await sync_module._resolve_entities(session, target, "rule")

    assert ids == [10, 20]
    _, params = session.executed[-1]
    assert params == {"database": "app_db", "schemas": ["public"], "regex": "^fact_"}


async def test_resolve_entities_index_filters_query():
    target = TargetYamlConfig(
        scope="index", type="hit_rate", names=[],
        filters={"database": "app_db", "tables": ["users"], "index_regex": "_pkey$"},
        warning=0.90, critical=0.80, direction="below",
    )
    session = FakeSession().on("metadata.index i", FakeResult(rows=[(33,)]))

    ids = await sync_module._resolve_entities(session, target, "rule")

    assert ids == [33]
    _, params = session.executed[-1]
    assert params == {"database": "app_db", "tables": ["users"], "regex": "_pkey$"}


async def test_resolve_entities_filters_empty_result_returns_empty():
    target = TargetYamlConfig(
        scope="table", type="growth_percent", names=[],
        filters={"database": "app_db"}, warning=20.0, critical=50.0, direction="above",
    )
    session = FakeSession().on("metadata.table t", FakeResult(rows=[]))

    ids = await sync_module._resolve_entities(session, target, "rule")
    assert ids == []



@pytest.mark.parametrize(
    "scope, name, query_fragment",
    [
        ("server", {"server": "srv1"}, "collector.server"),
        ("database", {"database": "app"}, "metadata.database"),
        ("table", {"schema": "public", "table": "users"}, "metadata.table t"),
        ("index", {"index": "idx"}, "metadata.index i"),
    ],
)
async def test_resolve_name_dispatches_per_scope(scope, name, query_fragment):
    session = FakeSession().on(query_fragment, FakeResult(first=(99,)))
    assert await sync_module._resolve_name(session, scope, name) == 99


async def test_resolve_name_returns_none_when_not_found():
    session = FakeSession().on("collector.server", FakeResult(first=None))
    assert await sync_module._resolve_name(session, "server", {"server": "ghost"}) is None



async def test_upsert_yaml_channels_encrypts_credentials():
    config = NotifierYamlConfig(
        channels={
            "slack": ChannelYamlConfig(
                name="slack", enabled=True,
                credentials={"webhook_url": "https://hooks/x"},
            )
        },
        rules=[],
    )
    session = FakeSession().on("INSERT INTO notifier.channel", FakeResult())

    import json
    captured = {}

    def fake_encrypt(payload):
        captured["payload"] = payload
        return "ENCRYPTED"

    with patch.object(sync_module, "encrypt", fake_encrypt):
        await sync_module._upsert_yaml_channels(session, config)

    assert captured["payload"] == json.dumps({"webhook_url": "https://hooks/x"})
    _, params = session.executed[-1]
    assert params == {"name": "slack", "enabled": True, "credentials": "ENCRYPTED"}


async def test_upsert_yaml_channels_skips_encryption_when_no_credentials():
    config = NotifierYamlConfig(
        channels={"slack": ChannelYamlConfig(name="slack", enabled=True, credentials={})},
        rules=[],
    )
    session = FakeSession().on("INSERT INTO notifier.channel", FakeResult())

    with patch.object(sync_module, "encrypt") as mock_encrypt:
        await sync_module._upsert_yaml_channels(session, config)

    mock_encrypt.assert_not_called()
    _, params = session.executed[-1]
    assert params["credentials"] is None



async def test_sync_config_seeds_upserts_rules_and_commits(monkeypatch):
    session = FakeSession()
    config = NotifierYamlConfig(
        channels={},
        rules=[RuleYamlConfig(name="r", interval=30, cooldown=600, window_minutes=10, enabled=True)],
    )

    calls = []

    async def fake_seed(s):
        calls.append("seed")

    async def fake_upsert_rule(s, r):
        calls.append("upsert_rule")

    async def fake_upsert_channels(s, c):
        calls.append("upsert_channels")

    monkeypatch.setattr(sync_module, "_seed_default_rule", fake_seed)
    monkeypatch.setattr(sync_module, "_upsert_rule", fake_upsert_rule)
    monkeypatch.setattr(sync_module, "_upsert_yaml_channels", fake_upsert_channels)

    await sync_module.sync_config(session, config)

    assert calls == ["seed", "upsert_rule", "upsert_channels"]
    assert session.committed is True
