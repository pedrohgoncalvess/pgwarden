import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from notifier.utils import decrypt_or_plain


@dataclass(frozen=True)
class ChannelRow:
    name: str
    credentials: dict[str, Any]


@dataclass(frozen=True)
class ScopeRow:
    scope_id: int
    scope: str
    type: str
    entity_id: int | None
    warning: float
    critical: float
    direction: str


@dataclass
class RuleRow:
    rule_id: int
    name: str
    interval: float
    cooldown: float
    window_minutes: float
    targets: list[ScopeRow] = field(default_factory=list)


_SCOPE_QUERIES = {
    "server": ("notifier.rule_server", "server_id"),
    "database": ("notifier.rule_database", "database_id"),
    "table": ("notifier.rule_table", "table_id"),
    "index": ("notifier.rule_index", "index_id"),
}


async def fetch_channels(session: AsyncSession) -> list[ChannelRow]:
    result = await session.execute(
        text("SELECT name, credentials FROM notifier.channel WHERE enabled = true")
    )
    channels = []
    for row in result.mappings():
        decrypted = decrypt_or_plain(row["credentials"])
        credentials = json.loads(decrypted) if decrypted else {}
        channels.append(ChannelRow(name=row["name"], credentials=credentials))
    return channels


async def fetch_rules(session: AsyncSession) -> list[RuleRow]:
    rules: dict[int, RuleRow] = {}

    for scope, (table, entity_column) in _SCOPE_QUERIES.items():
        result = await session.execute(
            text(
                f"""
                SELECT r.id AS rule_id, r.name, r.interval_seconds, r.cooldown_seconds, r.window_minutes,
                       s.id AS scope_id, s.type, s.{entity_column} AS entity_id,
                       s.warning, s.critical, s.direction
                FROM notifier.rule r
                JOIN {table} s ON s.rule_id = r.id
                WHERE r.enabled
                """
            )
        )
        for row in result.mappings():
            rule = rules.setdefault(
                row["rule_id"],
                RuleRow(
                    rule_id=row["rule_id"],
                    name=row["name"],
                    interval=row["interval_seconds"],
                    cooldown=row["cooldown_seconds"],
                    window_minutes=row["window_minutes"],
                ),
            )
            rule.targets.append(
                ScopeRow(
                    scope_id=row["scope_id"],
                    scope=scope,
                    type=row["type"],
                    entity_id=row["entity_id"],
                    warning=row["warning"],
                    critical=row["critical"],
                    direction=row["direction"],
                )
            )

    return list(rules.values())
