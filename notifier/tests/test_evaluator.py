import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from notifier.services.evaluator import Evaluator


class FakeChannel:
    def __init__(self, name="fake", fail_for=None, always_fail=False):
        self.name = name
        self.fail_for = fail_for or set()
        self.always_fail = always_fail
        self.sent = []
        self.calls = 0

    async def send(self, alert):
        self.calls += 1
        if self.always_fail or alert.entity in self.fail_for:
            raise RuntimeError(f"Channel {self.name} failed")
        self.sent.append(alert)


@pytest.fixture
def mock_fetch_last_time():
    with patch("notifier.services.evaluator.fetch_last_notification_time", new_callable=AsyncMock) as m:
        m.return_value = None
        yield m


@pytest.fixture
def mock_sleep():
    with patch("notifier.services.evaluator.asyncio.sleep", new_callable=AsyncMock) as m:
        yield m


async def test_dispatch_returns_only_delivered(make_alert):
    evaluator = Evaluator()
    alert1 = make_alert(entity="entity1")
    alert2 = make_alert(entity="entity2")
    
    ch1 = FakeChannel("ch1")
    ch2 = FakeChannel("ch2", fail_for={"entity1"})
    
    delivered = await evaluator._dispatch([alert1, alert2], [ch1, ch2])
    
    assert len(delivered) == 2
    assert alert1 in delivered
    assert alert2 in delivered
    
    assert len(ch1.sent) == 2
    assert len(ch2.sent) == 1


async def test_dispatch_all_channels_fail_returns_empty(make_alert, mock_sleep):
    evaluator = Evaluator()
    alert1 = make_alert(entity="entity1")
    
    ch1 = FakeChannel("ch1", always_fail=True)
    ch2 = FakeChannel("ch2", always_fail=True)
    
    delivered = await evaluator._dispatch([alert1], [ch1, ch2])
    
    assert delivered == []
    assert ch1.calls == 3
    assert ch2.calls == 3


async def test_dispatch_concurrent(make_alert):
    evaluator = Evaluator()
    alert1 = make_alert(entity="entity1")
    
    class SlowChannel:
        def __init__(self, name):
            self.name = name
            self.called = False

        async def send(self, alert):
            self.called = True
            await asyncio.sleep(0.05)

    ch1 = SlowChannel("ch1")
    ch2 = SlowChannel("ch2")
    
    start = asyncio.get_running_loop().time()
    await evaluator._dispatch([alert1], [ch1, ch2])
    end = asyncio.get_running_loop().time()
    
    assert ch1.called
    assert ch2.called
    assert end - start < 0.1  # Concurrency means it shouldn't take 0.1s (0.05 + 0.05)


async def test_send_with_retry_succeeds_on_second_attempt(make_alert, mock_sleep):
    evaluator = Evaluator()
    alert = make_alert()
    
    class FlakyChannel:
        def __init__(self):
            self.calls = 0
            self.name = "flaky"
            
        async def send(self, a):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("Failed first try")
                
    ch = FlakyChannel()
    await evaluator._send_with_retry(ch, alert)
    assert ch.calls == 2


async def test_send_with_retry_exhausts_retries(make_alert, mock_sleep):
    evaluator = Evaluator()
    alert = make_alert()
    
    ch = FakeChannel("ch1", always_fail=True)
    
    with pytest.raises(RuntimeError):
        await evaluator._send_with_retry(ch, alert)
        
    assert ch.calls == 3


async def test_cooldown_suppresses_duplicate(fake_session, mock_fetch_last_time):
    evaluator = Evaluator()
    evaluator._mark_sent("entity1", "critical", "cpu_percent")
    
    is_in_cooldown = await evaluator._in_cooldown(fake_session, "entity1", "critical", "cpu_percent", 5.0)
    assert is_in_cooldown is True
    mock_fetch_last_time.assert_not_called()


async def test_cooldown_allows_after_expiry(fake_session, mock_fetch_last_time):
    evaluator = Evaluator()
    evaluator._mark_sent("entity1", "critical", "cpu_percent")

    # Manually set the last-sent time to well beyond the cooldown window.
    evaluator._last_sent[("entity1", "critical", "cpu_percent")] = (
        datetime.now(timezone.utc) - timedelta(minutes=6)
    )

    is_in_cooldown = await evaluator._in_cooldown(fake_session, "entity1", "critical", "cpu_percent", 5.0)
    assert is_in_cooldown is False


async def test_undo_sent_removes_cooldown(fake_session, mock_fetch_last_time, make_alert):
    evaluator = Evaluator()
    alert = make_alert(entity="entity1", severity="critical", rule="cpu_percent")
    
    evaluator._mark_sent("entity1", "critical", "cpu_percent")
    assert await evaluator._in_cooldown(fake_session, "entity1", "critical", "cpu_percent", 5.0) is True
    
    evaluator._undo_sent(alert)
    assert await evaluator._in_cooldown(fake_session, "entity1", "critical", "cpu_percent", 5.0) is False


async def test_notification_only_after_dispatch(make_alert):
    shutdown_event = asyncio.Event()
    evaluator = Evaluator(shutdown_event=shutdown_event)
    
    alert1 = make_alert(entity="entity1")
    alert2 = make_alert(entity="entity2")
    
    rule = MagicMock()
    rule.rule_id = 1
    rule.interval = 10
    
    async def mock_fetch_rules(session):
        return [rule]
        
    async def mock_fetch_channels(session):
        return []

    evaluator._evaluate_rule = AsyncMock(return_value=[alert1, alert2])
    
    async def mock_dispatch(alerts, channels):
        shutdown_event.set()
        return [alert1]
        
    evaluator._dispatch = AsyncMock(side_effect=mock_dispatch)
    
    class MockSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def commit(self): pass
        
    def mock_connect():
        return MockSession()
    
    with patch("notifier.services.evaluator.fetch_rules", mock_fetch_rules), \
         patch("notifier.services.evaluator.fetch_channels", mock_fetch_channels), \
         patch("notifier.services.evaluator.build_channels", return_value=[]), \
         patch("notifier.services.evaluator.insert_notification", new_callable=AsyncMock) as mock_insert:
         
        await evaluator.run_forever(mock_connect)
        
        mock_insert.assert_called_once_with(ANY, alert1)
