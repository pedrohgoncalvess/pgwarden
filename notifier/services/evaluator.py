import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from notifier.channels import Alert, Channel, build_channels
from notifier.config.load import Threshold
from notifier.database import fetch_channels, fetch_rules
from notifier.database.queries import RuleRow
from notifier.services.notifications import insert_notification
from notifier.services.rules import RULE_TYPES


logger = logging.getLogger(__name__)

_DEFAULT_TICK_SECONDS = 5.0
_MAX_TICK_SECONDS = 60.0


class Evaluator:
    def __init__(self):
        self._last_sent: dict[tuple[int, str, str], datetime] = {}
        self._next_run: dict[int, float] = {}

    async def run_forever(self, connect) -> None:
        while True:
            delay = _DEFAULT_TICK_SECONDS
            try:
                async with connect() as session:
                    rules = await fetch_rules(session)
                    channels = build_channels(await fetch_channels(session))

                    now = time.monotonic()
                    due_rules = [rule for rule in rules if now >= self._next_run.get(rule.rule_id, 0.0)]
                    for rule in due_rules:
                        alerts = await self._evaluate_rule(session, rule)
                        for alert in alerts:
                            try:
                                await insert_notification(session, alert)
                            except Exception:
                                logger.exception("Falha ao registrar notificação %s", alert.rule)
                        await self._dispatch(alerts, channels)
                        self._next_run[rule.rule_id] = now + rule.interval

                    if due_rules:
                        await session.commit()

                    live_ids = {rule.rule_id for rule in rules}
                    self._next_run = {k: v for k, v in self._next_run.items() if k in live_ids}

                    upcoming = [run_at - now for run_at in self._next_run.values()]
                    if upcoming:
                        delay = min(upcoming)
            except Exception:
                logger.exception("Falha no ciclo de avaliação do notifier")

            await asyncio.sleep(min(max(delay, 1.0), _MAX_TICK_SECONDS))

    async def _evaluate_rule(self, session: AsyncSession, rule: RuleRow) -> list[Alert]:
        alerts: list[Alert] = []

        for target in rule.targets:
            rule_type = RULE_TYPES.get((target.scope, target.type))
            if rule_type is None:
                continue

            threshold = Threshold(target.warning, target.critical, target.direction)
            try:
                result = await session.execute(
                    text(rule_type.query),
                    {"window": rule.window_minutes, "entity_id": target.entity_id},
                )
            except Exception:
                logger.exception("Falha ao avaliar %s/%s (regra %s)", target.scope, target.type, rule.name)
                continue

            for row in result.mappings():
                mapped = rule_type.mapper(row)
                if mapped is None:
                    continue

                entity, value = mapped
                severity = threshold.severity_for(value)
                if severity is None:
                    continue

                if self._in_cooldown(target.scope_id, entity, severity, rule.cooldown):
                    continue

                alerts.append(
                    Alert(
                        rule=target.type,
                        severity=severity,
                        entity=entity,
                        message=rule_type.message,
                        value=value,
                        threshold=threshold.critical if severity == "critical" else threshold.warning,
                        scope=target.scope,
                        entity_id=target.entity_id,
                        rule_name=rule.name,
                        window_minutes=rule.window_minutes,
                    )
                )
                self._mark_sent(target.scope_id, entity, severity)

        return alerts

    async def _dispatch(self, alerts: list[Alert], channels: list[Channel]) -> None:
        for alert in alerts:
            for channel in channels:
                try:
                    await channel.send(alert)
                except Exception:
                    logger.exception(
                        "Falha ao enviar alerta %s para o canal %s", alert.rule, channel.name
                    )
            logger.info(
                "Alerta [%s] %s em %s: %s",
                alert.severity, alert.rule, alert.entity, alert.message,
            )

    def _in_cooldown(self, scope_id: int, entity: str, severity: str, cooldown: float) -> bool:
        last = self._last_sent.get((scope_id, entity, severity))
        if last is None:
            return False
        return datetime.now(timezone.utc) - last < timedelta(seconds=cooldown)

    def _mark_sent(self, scope_id: int, entity: str, severity: str) -> None:
        self._last_sent[(scope_id, entity, severity)] = datetime.now(timezone.utc)
