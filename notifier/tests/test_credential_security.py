import importlib.util
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from cryptography.fernet import Fernet

from notifier.channels.slack import SlackChannel
from notifier.channels.discord import DiscordChannel
from notifier.channels.teams import TeamsChannel
from notifier.channels import build_channels
from notifier.database.queries import ChannelRow
from notifier.database.credential_migration import migrate_credentials
from notifier.database.queries import fetch_channels
from notifier.services.evaluator import Evaluator
from notifier.utils.crypto import decrypt, encrypt

# Load the API's dependency-free validator without importing the API application.
spec = importlib.util.spec_from_file_location(
    "credential_validation",
    Path(__file__).resolve().parents[2] / "api/app/notifier/credentials.py",
)
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self.rows


@pytest.mark.parametrize("name", ["slack", "discord", "teams"])
def test_webhook_replacement_requires_complete_https_url(name):
    validation.validate_credentials(name, {"webhook_url": "https://example.com/secret"})
    for invalid in ({}, {"webhook_url": ""}, {"webhook_url": "http://example.com/secret"}):
        with pytest.raises(ValueError):
            validation.validate_credentials(name, invalid)


def test_smtp_replacement_requires_every_field_and_auth_pair():
    credentials = dict(host="smtp.example.com", port=587, username="u", password="secret",
                       to=["recipient@example.com"], **{"from": "sender@example.com"})
    validation.validate_credentials("email", credentials)
    for field in credentials:
        with pytest.raises(ValueError):
            validation.validate_credentials("email", {k: v for k, v in credentials.items() if k != field})
    with pytest.raises(ValueError):
        validation.validate_credentials("email", {**credentials, "password": ""})
    validation.validate_credentials("email", {**credentials, "username": "", "password": ""})


async def test_migration_encrypts_plaintext_and_preserves_ciphertext():
    plain = json.dumps({"webhook_url": "https://example.com/secret"})
    encrypted = encrypt(plain)
    session = AsyncMock()
    session.execute.return_value = Result([
        {"id": 1, "credentials": plain}, {"id": 2, "credentials": encrypted},
    ])
    assert await migrate_credentials(session) == 1
    assert session.execute.call_count == 2
    params = session.execute.call_args.args[1]
    assert params["id"] == 1
    assert params["credentials"] != plain
    assert decrypt(params["credentials"]) == plain


async def test_migration_rejects_wrong_key_without_exposing_ciphertext():
    encrypted = Fernet(Fernet.generate_key()).encrypt(b'{"password":"secret"}').decode()
    session = AsyncMock()
    session.execute.return_value = Result([{"id": 1, "credentials": encrypted}])
    with pytest.raises(RuntimeError) as error:
        await migrate_credentials(session)
    assert encrypted not in str(error.value)
    assert session.execute.call_count == 1


async def test_plaintext_channel_skipped_without_blocking_healthy_channel(caplog):
    session = AsyncMock()
    session.execute.return_value = Result([
        {"name": "slack", "credentials": '{"password":"private-secret"}'},
        {"name": "discord", "credentials": encrypt('{"webhook_url":"https://example.com/new"}')},
    ])
    rows = await fetch_channels(session)
    assert [row.name for row in rows] == ["discord"]
    assert "private-secret" not in caplog.text


def test_invalid_channel_configuration_does_not_log_values(caplog):
    assert build_channels([ChannelRow(
        name="email", credentials={"host": "smtp.example.com", "port": "private-secret"}
    )]) == []
    assert "private-secret" not in caplog.text


async def test_smtp_failure_does_not_log_credentials(make_alert, caplog):
    channel = AsyncMock()
    channel.name = "email"
    channel.send.side_effect = RuntimeError("SMTP authentication failed: private-password")
    with patch("notifier.services.evaluator.asyncio.sleep", new_callable=AsyncMock):
        await Evaluator()._dispatch([make_alert()], [channel])
    assert "private-password" not in caplog.text


@pytest.mark.parametrize("channel_type", [SlackChannel, DiscordChannel, TeamsChannel])
@pytest.mark.parametrize("status", [200, 403])
async def test_dispatch_logs_do_not_expose_webhooks(channel_type, status, make_alert, caplog):
    # Applies the same HTTP logging policy as the notifier entry point.
    import notifier.main  # noqa: F401
    caplog.set_level(logging.INFO)
    url = "https://example.com/private-webhook-secret?token=private-token"
    transport = httpx.MockTransport(lambda request: httpx.Response(status))
    async with httpx.AsyncClient(transport=transport) as client:
        channel = channel_type(url, client=client)
        with patch("notifier.services.evaluator.asyncio.sleep", new_callable=AsyncMock):
            await Evaluator()._dispatch([make_alert()], [channel])
    assert "private-webhook-secret" not in caplog.text
    assert "private-token" not in caplog.text
