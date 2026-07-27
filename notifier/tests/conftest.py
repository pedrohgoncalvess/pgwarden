import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from notifier.channels.base import Alert


@pytest.fixture
def make_alert():
    def _make_alert(
        rule="cpu_percent",
        severity="critical",
        entity="server local",
        message="Uso de CPU acima do threshold",
        value=97.5,
        threshold=95.0,
        scope="",
        entity_id=None,
        rule_name="",
        window_minutes=5.0
    ):
        return Alert(
            rule=rule,
            severity=severity,
            entity=entity,
            message=message,
            value=value,
            threshold=threshold,
            scope=scope,
            entity_id=entity_id,
            rule_name=rule_name,
            window_minutes=window_minutes
        )
    return _make_alert


@pytest.fixture
def fake_session():
    return AsyncMock()


@pytest.fixture
def shutdown_event():
    return asyncio.Event()
