"""Tests for notifier.database.queries (SQL building + row mapping).

The real SQL is exercised against a fake session that returns canned rows;
no database connection is required.
"""

from unittest.mock import patch

from notifier.database import queries


class MappingsResult:
    """Mimics SQLAlchemy Result.mappings()."""

    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class QueuedSession:
    """Returns successive canned results, one per execute() call."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    async def execute(self, query, params=None):
        self.calls.append((str(query), params))
        if self._results:
            return self._results.pop(0)
        return MappingsResult([])



async def test_fetch_channels_decrypts_and_parses_credentials():
    rows = [
        {"name": "slack", "credentials": '{"webhook_url": "https://hooks/x"}'},
        {"name": "email", "credentials": ""},
    ]
    session = QueuedSession([MappingsResult(rows)])

    def fake_decrypt(value):
        return value if value == "" else value

    with patch.object(queries, "decrypt", lambda v: v):
        channels = await queries.fetch_channels(session)

    assert len(channels) == 2
    assert channels[0].name == "slack"
    assert channels[0].credentials == {"webhook_url": "https://hooks/x"}
    assert channels[1].name == "email"
    assert channels[1].credentials == {}


async def test_fetch_channels_uses_strict_decryption():
    rows = [{"name": "slack", "credentials": "CIPHERTEXT"}]
    session = QueuedSession([MappingsResult(rows)])

    with patch.object(queries, "decrypt", return_value='{"webhook_url": "u"}') as m:
        channels = await queries.fetch_channels(session)

    m.assert_called_once_with("CIPHERTEXT")
    assert channels[0].credentials == {"webhook_url": "u"}



def _scope_row(rule_id, scope, type_, entity_id=None):
    return {
        "rule_id": rule_id,
        "name": f"rule-{rule_id}",
        "interval_seconds": 60,
        "cooldown_seconds": 1800,
        "window_minutes": 5,
        "scope_id": rule_id * 100,
        "type": type_,
        "entity_id": entity_id,
        "warning": 85.0,
        "critical": 95.0,
        "direction": "above",
    }


async def test_fetch_rules_builds_rule_tree_from_scope_results():
    results = [
        MappingsResult([_scope_row(1, "server", "cpu_percent", 10)]),
        MappingsResult([_scope_row(1, "database", "cache_hit_ratio", 20)]),
        MappingsResult([]),
        MappingsResult([]),
    ]
    session = QueuedSession(results)

    rules = await queries.fetch_rules(session)

    assert len(rules) == 1
    rule = rules[0]
    assert rule.rule_id == 1
    assert rule.name == "rule-1"
    assert rule.interval == 60
    assert rule.cooldown == 1800
    assert rule.window_minutes == 5
    assert {t.scope for t in rule.targets} == {"server", "database"}
    server_target = next(t for t in rule.targets if t.scope == "server")
    assert server_target.type == "cpu_percent"
    assert server_target.entity_id == 10
    assert server_target.warning == 85.0


async def test_fetch_rules_aggregates_multiple_targets_per_rule():
    results = [
        MappingsResult([
            _scope_row(5, "server", "cpu_percent", 1),
            _scope_row(5, "server", "ram_percent", 1),
        ]),
        MappingsResult([]),
        MappingsResult([]),
        MappingsResult([]),
    ]
    session = QueuedSession(results)

    rules = await queries.fetch_rules(session)

    assert len(rules) == 1
    assert {t.type for t in rules[0].targets} == {"cpu_percent", "ram_percent"}


async def test_fetch_rules_returns_empty_when_no_rows():
    session = QueuedSession([MappingsResult([])] * 4)
    rules = await queries.fetch_rules(session)
    assert rules == []



async def test_fetch_last_notification_time_returns_timestamp():
    from datetime import datetime

    session = QueuedSession([MappingsResult([(datetime(2024, 1, 1, 12, 0, 0),)])])

    result = await queries.fetch_last_notification_time(session, "srv1", "critical", "cpu_percent")

    assert result == datetime(2024, 1, 1, 12, 0, 0)
    _, params = session.calls[0]
    assert params == {"entity": "srv1", "severity": "critical", "type": "cpu_percent"}


async def test_fetch_last_notification_time_returns_none_when_no_match():
    session = QueuedSession([MappingsResult([])])
    result = await queries.fetch_last_notification_time(session, "srv1", "critical", "cpu_percent")
    assert result is None
