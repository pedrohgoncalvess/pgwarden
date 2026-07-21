from notifier.channels import build_channels
from notifier.channels.base import Alert
from notifier.database.queries import ChannelRow


def make_alert() -> Alert:
    return Alert(
        rule="cpu_percent",
        severity="critical",
        entity="server local",
        message="Uso de CPU acima do threshold",
        value=97.5,
        threshold=95.0,
    )


def test_alert_format_text():
    text = make_alert().format_text()
    assert "[CRITICAL] cpu_percent" in text
    assert "server local" in text
    assert "97.5" in text
    assert "95" in text


def test_build_channels_from_rows():
    rows = [
        ChannelRow(name="slack", credentials={"webhook_url": "https://hooks.slack.com/x"}),
        ChannelRow(name="discord", credentials={"webhook_url": "https://discord.com/api/webhooks/x"}),
        ChannelRow(name="teams", credentials={"webhook_url": "https://teams.webhook/x"}),
        ChannelRow(
            name="email",
            credentials={
                "host": "smtp.example.com",
                "port": 465,
                "username": "u",
                "password": "p",
                "from": "a@example.com",
                "to": "b@example.com, c@example.com",
            },
        ),
    ]
    channels = build_channels(rows)
    assert [c.name for c in channels] == ["slack", "discord", "teams", "email"]


def test_build_channels_skips_missing_credentials():
    rows = [ChannelRow(name="slack", credentials={})]
    assert build_channels(rows) == []


def test_build_channels_skips_unknown_channel():
    rows = [ChannelRow(name="pagerduty", credentials={"token": "x"})]
    assert build_channels(rows) == []


def test_slack_payload():
    from unittest.mock import patch

    from notifier.channels.slack import SlackChannel

    alert = make_alert()
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    import asyncio

    with patch("notifier.channels.slack.httpx.AsyncClient", FakeClient):
        asyncio.run(SlackChannel("https://hooks.slack.com/x").send(alert))

    assert captured["url"] == "https://hooks.slack.com/x"
    assert "[CRITICAL] cpu_percent" in captured["json"]["text"]


def test_teams_payload_shape():
    import asyncio
    from unittest.mock import patch

    from notifier.channels.teams import TeamsChannel

    alert = make_alert()
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None):
            captured["json"] = json
            return FakeResponse()

    with patch("notifier.channels.teams.httpx.AsyncClient", FakeClient):
        asyncio.run(TeamsChannel("https://teams.webhook/x").send(alert))

    payload = captured["json"]
    assert payload["@type"] == "MessageCard"
    assert payload["themeColor"] == "FF0000"
    facts = {f["name"]: f["value"] for f in payload["sections"][0]["facts"]}
    assert facts["Entidade"] == "server local"
