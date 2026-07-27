from unittest.mock import patch
import httpx
import pytest

from notifier.channels import build_channels
from notifier.database.queries import ChannelRow
from notifier.channels.slack import SlackChannel
from notifier.channels.teams import TeamsChannel


def test_alert_format_text(make_alert):
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


async def test_slack_payload(make_alert):
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

    with patch("notifier.channels.slack.httpx.AsyncClient", FakeClient):
        await SlackChannel("https://hooks.slack.com/x").send(alert)

    assert captured["url"] == "https://hooks.slack.com/x"
    assert "[CRITICAL] cpu_percent" in captured["json"]["text"]


async def test_teams_payload_shape(make_alert):
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
        await TeamsChannel("https://teams.webhook/x").send(alert)

    payload = captured["json"]
    assert payload["@type"] == "MessageCard"
    assert payload["themeColor"] == "FF0000"
    facts = {f["name"]: f["value"] for f in payload["sections"][0]["facts"]}
    assert facts["Entidade"] == "server local"


async def test_slack_uses_shared_client():
    client = httpx.AsyncClient(timeout=10)
    ch = SlackChannel("https://hooks.slack.com/x", client=client)
    assert ch._client is client
    await client.aclose()


# ---------------------------------------------------------------------------
# Alert.format_plain
# ---------------------------------------------------------------------------

def test_alert_format_plain(make_alert):
    text = make_alert().format_plain()
    assert "[CRITICAL] cpu_percent" in text
    assert "server local" in text
    assert "97.5" in text
    assert "95" in text


# ---------------------------------------------------------------------------
# DiscordChannel.send payload
# ---------------------------------------------------------------------------

async def test_discord_payload_shape(make_alert):
    from notifier.channels.discord import DiscordChannel

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

    with patch("notifier.channels.discord.httpx.AsyncClient", FakeClient):
        await DiscordChannel("https://discord.com/api/webhooks/x").send(alert)

    payload = captured["json"]
    assert captured["url"] == "https://discord.com/api/webhooks/x"
    assert payload["embeds"][0]["title"] == "[CRITICAL] cpu_percent"
    assert payload["embeds"][0]["color"] == int("FF0000", 16)
    assert "server local" in payload["embeds"][0]["description"]


# ---------------------------------------------------------------------------
# EmailChannel.send payload
# ---------------------------------------------------------------------------

async def test_email_payload_shape(make_alert):
    from notifier.channels.email import EmailChannel

    alert = make_alert()
    captured = {}

    async def fake_send(message, **kwargs):
        captured["message"] = message
        captured["kwargs"] = kwargs

    with patch("notifier.channels.email.aiosmtplib.send", fake_send):
        channel = EmailChannel(
            host="smtp.example.com", port=465, username="u", password="p",
            sender="a@example.com", recipients=["b@example.com", "c@example.com"],
        )
        await channel.send(alert)

    message = captured["message"]
    assert message["From"] == "a@example.com"
    assert message["To"] == "b@example.com, c@example.com"
    assert "[CRITICAL] cpu_percent" in message["Subject"]
    # Port 465 => implicit TLS (use_tls=True, start_tls=False).
    assert captured["kwargs"]["use_tls"] is True
    assert captured["kwargs"]["start_tls"] is False
    assert captured["kwargs"]["hostname"] == "smtp.example.com"
    assert captured["kwargs"]["port"] == 465


async def test_email_uses_starttls_on_non_465_port(make_alert):
    from notifier.channels.email import EmailChannel

    alert = make_alert()
    captured = {}

    async def fake_send(message, **kwargs):
        captured["kwargs"] = kwargs

    with patch("notifier.channels.email.aiosmtplib.send", fake_send):
        channel = EmailChannel(
            host="smtp.example.com", port=587, username=None, password=None,
            sender="a@example.com", recipients=["b@example.com"],
        )
        await channel.send(alert)

    assert captured["kwargs"]["use_tls"] is False
    assert captured["kwargs"]["start_tls"] is True

