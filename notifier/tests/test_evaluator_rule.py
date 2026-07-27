"""Tests for Evaluator._evaluate_rule — the real alert-detection logic.

Unlike test_evaluator.py (which mocks _evaluate_rule out), these tests drive
the actual threshold evaluation, mapping and cooldown path.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from notifier.database.queries import RuleRow, ScopeRow
from notifier.services.evaluator import Evaluator


class MappingsResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return list(self._rows)


class ExecSession:
    """Returns canned mapping rows for the metric query execute() call."""

    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    async def execute(self, query, params=None):
        self.calls.append((str(query), params))
        return MappingsResult(self._rows)


def _rule(*targets, rule_id=1, cooldown=100, window=5, name="r1"):
    rule = RuleRow(
        rule_id=rule_id, name=name, interval=10,
        cooldown=cooldown, window_minutes=window,
    )
    rule.targets = list(targets)
    return rule


@pytest.fixture
def mock_fetch_last_time():
    with patch(
        "notifier.services.evaluator.fetch_last_notification_time",
        new_callable=AsyncMock,
    ) as m:
        m.return_value = None
        yield m


async def test_evaluate_rule_emits_critical_alert(mock_fetch_last_time):
    target = ScopeRow(
        scope_id=1, scope="server", type="cpu_percent", entity_id=None,
        warning=85.0, critical=95.0, direction="above",
    )
    session = ExecSession([{"entity": "srv1", "value": 97.0}])
    evaluator = Evaluator()

    alerts = await evaluator._evaluate_rule(session, _rule(target))

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.severity == "critical"
    assert alert.entity == "srv1"
    assert alert.value == 97.0
    assert alert.threshold == 95.0
    assert alert.rule == "cpu_percent"
    assert alert.scope == "server"
    assert ("srv1", "critical", "cpu_percent") in evaluator._last_sent


async def test_evaluate_rule_emits_warning_below_critical(mock_fetch_last_time):
    target = ScopeRow(
        scope_id=1, scope="server", type="cpu_percent", entity_id=None,
        warning=85.0, critical=95.0, direction="above",
    )
    session = ExecSession([{"entity": "srv1", "value": 88.0}])
    evaluator = Evaluator()

    alerts = await evaluator._evaluate_rule(session, _rule(target))

    assert len(alerts) == 1
    assert alerts[0].severity == "warning"
    assert alerts[0].threshold == 85.0


async def test_evaluate_rule_skips_values_under_threshold(mock_fetch_last_time):
    target = ScopeRow(
        scope_id=1, scope="server", type="cpu_percent", entity_id=None,
        warning=85.0, critical=95.0, direction="above",
    )
    session = ExecSession([{"entity": "srv1", "value": 50.0}])
    evaluator = Evaluator()

    alerts = await evaluator._evaluate_rule(session, _rule(target))

    assert alerts == []


async def test_evaluate_rule_respects_below_direction(mock_fetch_last_time):
    target = ScopeRow(
        scope_id=1, scope="index", type="hit_rate", entity_id=None,
        warning=0.90, critical=0.80, direction="below",
    )
    session = ExecSession([{"entity": "idx1", "value": 0.75}])
    evaluator = Evaluator()

    alerts = await evaluator._evaluate_rule(session, _rule(target))

    assert len(alerts) == 1
    assert alerts[0].severity == "critical"
    assert alerts[0].threshold == 0.80



async def test_evaluate_rule_skips_null_metric_values(mock_fetch_last_time):
    target = ScopeRow(
        scope_id=1, scope="server", type="cpu_percent", entity_id=None,
        warning=85.0, critical=95.0, direction="above",
    )
    # _simple mapper returns None when value is None.
    session = ExecSession([{"entity": "srv1", "value": None}])
    evaluator = Evaluator()

    alerts = await evaluator._evaluate_rule(session, _rule(target))

    assert alerts == []


async def test_evaluate_rule_cooldown_suppresses_alert(mock_fetch_last_time):
    target = ScopeRow(
        scope_id=1, scope="server", type="cpu_percent", entity_id=None,
        warning=85.0, critical=95.0, direction="above",
    )
    session = ExecSession([{"entity": "srv1", "value": 97.0}])
    evaluator = Evaluator()

    evaluator._mark_sent("srv1", "critical", "cpu_percent")

    alerts = await evaluator._evaluate_rule(session, _rule(target))

    assert alerts == []
    mock_fetch_last_time.assert_not_called()


async def test_evaluate_rule_db_cooldown_suppresses_alert(mock_fetch_last_time):
    target = ScopeRow(
        scope_id=1, scope="server", type="cpu_percent", entity_id=None,
        warning=85.0, critical=95.0, direction="above",
    )
    session = ExecSession([{"entity": "srv1", "value": 97.0}])
    evaluator = Evaluator()

    mock_fetch_last_time.return_value = datetime.now(timezone.utc)

    alerts = await evaluator._evaluate_rule(session, _rule(target, cooldown=1800))

    assert alerts == []


async def test_evaluate_rule_skips_unknown_target_type(mock_fetch_last_time):
    target = ScopeRow(
        scope_id=1, scope="server", type="does_not_exist", entity_id=None,
        warning=85.0, critical=95.0, direction="above",
    )
    session = ExecSession([])
    evaluator = Evaluator()

    alerts = await evaluator._evaluate_rule(session, _rule(target))

    assert alerts == []
    assert session.calls == []


async def test_evaluate_rule_continues_after_query_failure(mock_fetch_last_time):
    target = ScopeRow(
        scope_id=1, scope="server", type="cpu_percent", entity_id=None,
        warning=85.0, critical=95.0, direction="above",
    )

    class FailingSession:
        async def execute(self, query, params=None):
            raise RuntimeError("DB down")

    evaluator = Evaluator()

    alerts = await evaluator._evaluate_rule(FailingSession(), _rule(target))

    assert alerts == []


async def test_evaluate_rule_passes_window_and_entity_id(mock_fetch_last_time):
    target = ScopeRow(
        scope_id=1, scope="server", type="cpu_percent", entity_id=42,
        warning=85.0, critical=95.0, direction="above",
    )
    session = ExecSession([{"entity": "srv1", "value": 97.0}])
    evaluator = Evaluator()

    await evaluator._evaluate_rule(session, _rule(target, window=15))

    _, params = session.calls[0]
    assert params == {"window": 15, "entity_id": 42}


async def test_evaluate_rule_dead_tuple_ratio_mapper(mock_fetch_last_time):
    target = ScopeRow(
        scope_id=1, scope="table", type="dead_tuple_ratio", entity_id=None,
        warning=0.2, critical=0.5, direction="above",
    )
    # dead/live = 4000/6000 -> 0.4 -> warning
    session = ExecSession([{"entity": "public.t", "n_dead_tup": 4000, "n_live_tup": 6000}])
    evaluator = Evaluator()

    alerts = await evaluator._evaluate_rule(session, _rule(target))

    assert len(alerts) == 1
    assert alerts[0].severity == "warning"
    assert alerts[0].value == 0.4

