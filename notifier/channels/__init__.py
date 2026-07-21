import logging

from notifier.channels.base import Alert, Channel
from notifier.channels.discord import DiscordChannel
from notifier.channels.email import EmailChannel
from notifier.channels.slack import SlackChannel
from notifier.channels.teams import TeamsChannel
from notifier.database.queries import ChannelRow


logger = logging.getLogger(__name__)


def build_channels(rows: list[ChannelRow]) -> list[Channel]:
    channels: list[Channel] = []
    for row in rows:
        builder = _BUILDERS.get(row.name)
        if builder is None:
            logger.warning("Canal desconhecido ignorado: %s", row.name)
            continue
        try:
            channels.append(builder(row.credentials))
        except ValueError as error:
            logger.warning("Canal %s ignorado: %s", row.name, error)
    return channels


def _required(credentials: dict, key: str) -> str:
    value = credentials.get(key)
    if not value:
        raise ValueError(f"credencial '{key}' ausente")
    return value


def _build_slack(credentials: dict) -> Channel:
    return SlackChannel(_required(credentials, "webhook_url"))


def _build_discord(credentials: dict) -> Channel:
    return DiscordChannel(_required(credentials, "webhook_url"))


def _build_teams(credentials: dict) -> Channel:
    return TeamsChannel(_required(credentials, "webhook_url"))


def _build_email(credentials: dict) -> Channel:
    recipients = credentials.get("to") or []
    if isinstance(recipients, str):
        recipients = [addr.strip() for addr in recipients.split(",") if addr.strip()]
    return EmailChannel(
        host=_required(credentials, "host"),
        port=int(credentials.get("port", 587)),
        username=credentials.get("username") or None,
        password=credentials.get("password") or None,
        sender=_required(credentials, "from"),
        recipients=recipients,
    )


_BUILDERS = {
    "slack": _build_slack,
    "discord": _build_discord,
    "teams": _build_teams,
    "email": _build_email,
}

__all__ = ["Alert", "Channel", "build_channels"]
