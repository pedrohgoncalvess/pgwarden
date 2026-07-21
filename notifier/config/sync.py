import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from notifier.config.load import NotifierYamlConfig, RuleYamlConfig, TargetYamlConfig
from notifier.services.rules import RULE_TYPES
from notifier.utils import encrypt


logger = logging.getLogger(__name__)

_SCOPE_TABLE = {
    "server": ("notifier.rule_server", "server_id"),
    "database": ("notifier.rule_database", "database_id"),
    "table": ("notifier.rule_table", "table_id"),
    "index": ("notifier.rule_index", "index_id"),
}


async def sync_config(session: AsyncSession, config: NotifierYamlConfig) -> None:
    await _seed_default_rule(session)
    for rule in config.rules:
        await _upsert_rule(session, rule)
    await _upsert_yaml_channels(session, config)
    await session.commit()


async def _seed_default_rule(session: AsyncSession) -> None:
    result = await session.execute(text("SELECT 1 FROM notifier.rule LIMIT 1"))
    if result.first() is not None:
        return

    rule_id = await _insert_rule(session, "default", 60, 1800, 5, True)
    for rule_type in RULE_TYPES.values():
        table, entity_column = _SCOPE_TABLE[rule_type.scope]
        await session.execute(
            text(
                f"""
                INSERT INTO {table} (rule_id, {entity_column}, type, warning, critical, direction)
                VALUES (:rule_id, NULL, :type, :warning, :critical, :direction)
                """
            ),
            {
                "rule_id": rule_id,
                "type": rule_type.type,
                "warning": rule_type.default_warning,
                "critical": rule_type.default_critical,
                "direction": rule_type.default_direction,
            },
        )


async def _upsert_rule(session: AsyncSession, rule: RuleYamlConfig) -> None:
    result = await session.execute(
        text(
            """
            INSERT INTO notifier.rule (name, interval_seconds, cooldown_seconds, window_minutes, enabled)
            VALUES (:name, :interval, :cooldown, :window, :enabled)
            ON CONFLICT (name) DO UPDATE SET
                interval_seconds = EXCLUDED.interval_seconds,
                cooldown_seconds = EXCLUDED.cooldown_seconds,
                window_minutes = EXCLUDED.window_minutes,
                enabled = EXCLUDED.enabled,
                updated_at = now()
            RETURNING id
            """
        ),
        {
            "name": rule.name,
            "interval": rule.interval,
            "cooldown": rule.cooldown,
            "window": rule.window_minutes,
            "enabled": rule.enabled,
        },
    )
    rule_id = result.scalar_one()

    for table, _ in _SCOPE_TABLE.values():
        await session.execute(text(f"DELETE FROM {table} WHERE rule_id = :rule_id"), {"rule_id": rule_id})

    for target in rule.targets:
        entity_ids = await _resolve_entities(session, target, rule.name)
        if not entity_ids:
            continue

        table, entity_column = _SCOPE_TABLE[target.scope]
        for entity_id in entity_ids:
            await session.execute(
                text(
                    f"""
                    INSERT INTO {table} (rule_id, {entity_column}, type, warning, critical, direction)
                    VALUES (:rule_id, :entity_id, :type, :warning, :critical, :direction)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "rule_id": rule_id,
                    "entity_id": entity_id,
                    "type": target.type,
                    "warning": target.warning,
                    "critical": target.critical,
                    "direction": target.direction,
                },
            )


async def _insert_rule(
    session: AsyncSession, name: str, interval: int, cooldown: int, window: int, enabled: bool
) -> int:
    result = await session.execute(
        text(
            """
            INSERT INTO notifier.rule (name, interval_seconds, cooldown_seconds, window_minutes, enabled)
            VALUES (:name, :interval, :cooldown, :window, :enabled)
            RETURNING id
            """
        ),
        {"name": name, "interval": interval, "cooldown": cooldown, "window": window, "enabled": enabled},
    )
    return result.scalar_one()


async def _resolve_entities(
    session: AsyncSession, target: TargetYamlConfig, rule_name: str
) -> list[int | None]:
    if target.names:
        ids: list[int | None] = []
        for name in target.names:
            entity_id = await _resolve_name(session, target.scope, name)
            if entity_id is None:
                logger.warning(
                    "Entidade %s não encontrada para o target %s/%s da regra %s — ignorada",
                    name, target.scope, target.type, rule_name,
                )
                continue
            ids.append(entity_id)
        return ids

    if not target.filters:
        return [None]

    if target.scope == "table":
        result = await session.execute(
            text(
                """
                SELECT t.id FROM metadata.table t
                JOIN metadata.database d ON d.id = t.database_id
                WHERE t.deleted_at IS NULL
                  AND (:database IS NULL OR d.db_name = :database)
                  AND (:schemas IS NULL OR t.schema_name = ANY(:schemas))
                  AND (:regex IS NULL OR t.name ~ :regex)
                """
            ),
            {
                "database": target.filters.get("database"),
                "schemas": target.filters.get("schemas"),
                "regex": target.filters.get("table_regex"),
            },
        )
        ids = [row[0] for row in result.fetchall()]
    elif target.scope == "index":
        result = await session.execute(
            text(
                """
                SELECT i.id FROM metadata.index i
                JOIN metadata.database d ON d.id = i.database_id
                JOIN metadata.table t ON t.id = i.table_id
                WHERE i.deleted_at IS NULL
                  AND (:database IS NULL OR d.db_name = :database)
                  AND (:tables IS NULL OR t.name = ANY(:tables))
                  AND (:regex IS NULL OR i.name ~ :regex)
                """
            ),
            {
                "database": target.filters.get("database"),
                "tables": target.filters.get("tables"),
                "regex": target.filters.get("index_regex"),
            },
        )
        ids = [row[0] for row in result.fetchall()]
    else:
        return [None]

    if not ids:
        logger.warning(
            "Nenhuma entidade encontrada para os filtros %s do target %s/%s da regra %s",
            target.filters, target.scope, target.type, rule_name,
        )
    return ids


async def _resolve_name(session: AsyncSession, scope: str, name: dict[str, str]) -> int | None:
    if scope == "server":
        result = await session.execute(
            text("SELECT id FROM collector.server WHERE name = :name"),
            {"name": name.get("server")},
        )
    elif scope == "database":
        result = await session.execute(
            text("SELECT id FROM metadata.database WHERE db_name = :name"),
            {"name": name.get("database")},
        )
    elif scope == "table":
        result = await session.execute(
            text(
                """
                SELECT t.id FROM metadata.table t
                JOIN metadata.database d ON d.id = t.database_id
                WHERE (:database IS NULL OR d.db_name = :database)
                  AND t.schema_name = :schema AND t.name = :table
                """
            ),
            {
                "database": name.get("database"),
                "schema": name.get("schema", "public"),
                "table": name.get("table"),
            },
        )
    else:
        result = await session.execute(
            text(
                """
                SELECT i.id FROM metadata.index i
                JOIN metadata.database d ON d.id = i.database_id
                WHERE (:database IS NULL OR d.db_name = :database)
                  AND i.name = :index
                """
            ),
            {"database": name.get("database"), "index": name.get("index")},
        )

    row = result.first()
    return row[0] if row else None


async def _upsert_yaml_channels(session: AsyncSession, config: NotifierYamlConfig) -> None:
    for channel in (config.channels or {}).values():
        credentials = encrypt(json.dumps(channel.credentials)) if channel.credentials else None
        await session.execute(
            text(
                """
                INSERT INTO notifier.channel (name, enabled, credentials)
                VALUES (:name, :enabled, :credentials)
                ON CONFLICT (name) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    credentials = COALESCE(EXCLUDED.credentials, notifier.channel.credentials),
                    updated_at = now()
                """
            ),
            {"name": channel.name, "enabled": channel.enabled, "credentials": credentials},
        )
