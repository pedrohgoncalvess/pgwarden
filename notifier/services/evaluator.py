import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from notifier.channels import Alert, Channel, build_channels
from notifier.config.load import Threshold
from notifier.database import fetch_channels, fetch_last_notification_time, fetch_rules
from notifier.database.heartbeat import touch_heartbeat
from notifier.database.queries import RuleRow
from notifier.services.notifications import insert_notification
from notifier.services.rules import RULE_TYPES


logger = logging.getLogger(__name__)

_DEFAULT_TICK_SECONDS = 5.0
_MAX_TICK_SECONDS = 60.0
_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 1.0


class Evaluator:
    def __init__(self, *, shutdown_event: asyncio.Event | None = None):
        self._last_sent: dict[tuple[str, str, str], datetime] = {}
        self._next_run: dict[int, float] = {}
        self._shutdown = shutdown_event or asyncio.Event()
        self._http_client: httpx.AsyncClient | None = None

    async def run_forever(self, connect) -> None:
        self._http_client = httpx.AsyncClient(timeout=10)
        try:
            while not self._shutdown.is_set():
                delay = _DEFAULT_TICK_SECONDS
                try:
                    async with connect() as session:
                        await touch_heartbeat(session)
                        await session.commit()
                        now = time.monotonic()
                        force_run = await _consume_force_run(session)
                        if force_run:
                            await session.commit()
                        has_due = force_run or any(
                            now >= self._next_run.get(rid, 0.0)
                            for rid in self._next_run
                        ) or not self._next_run

                        # Avoid database reads while no rule can run.
                        if has_due:
                            rules = await fetch_rules(session)
                            channels = build_channels(
                                await fetch_channels(session),
                                client=self._http_client,
                            )

                            due_rules = [
                                rule for rule in rules
                                if force_run or now >= self._next_run.get(rule.rule_id, 0.0)
                            ]
                            for rule in due_rules:
                                alerts = await self._evaluate_rule(session, rule)
                                delivered = await self._dispatch(alerts, channels)
                                for alert in delivered:
                                    try:
                                        await insert_notification(session, alert)
                                    except Exception:
                                        logger.exception(
                                            "Falha ao registrar notificação %s", alert.rule,
                                        )
                                self._next_run[rule.rule_id] = now + rule.interval

                            if due_rules:
                                await session.commit()

                            live_ids = {rule.rule_id for rule in rules}
                            self._next_run = {
                                k: v for k, v in self._next_run.items() if k in live_ids
                            }

                        upcoming = [run_at - now for run_at in self._next_run.values()]
                        if upcoming:
                            delay = min(upcoming)
                except Exception:
                    logger.exception("Falha no ciclo de avaliação do notifier")

                # Sleep in small increments so we can respond to shutdown quickly.
                sleep_time = min(max(delay, 1.0), _MAX_TICK_SECONDS)
                try:
                    await asyncio.wait_for(
                        self._shutdown.wait(), timeout=sleep_time,
                    )
                    break
                except asyncio.TimeoutError:
                    pass
        finally:
            await self._http_client.aclose()
            self._http_client = None

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

                if await self._in_cooldown(
                    session, entity, severity, target.type, rule.cooldown,
                ):
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
                self._mark_sent(entity, severity, target.type)

        return alerts

    async def _dispatch(self, alerts: list[Alert], channels: list[Channel]) -> list[Alert]:
        """Send alerts to all channels concurrently.

        Returns the list of alerts for which at least one channel
        succeeded — only these should be persisted as notifications.
        """
        if not alerts or not channels:
            return []

        delivered: list[Alert] = []

        for alert in alerts:
            tasks = [
                self._send_with_retry(channel, alert)
                for channel in channels
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            any_success = False
            for channel, result in zip(channels, results):
                if isinstance(result, Exception):
                    logger.exception(
                        "Falha ao enviar alerta %s para o canal %s: %s",
                        alert.rule, channel.name, result,
                    )
                else:
                    any_success = True

            if any_success:
                delivered.append(alert)
                logger.info(
                    "Alerta [%s] %s em %s: %s",
                    alert.severity, alert.rule, alert.entity, alert.message,
                )
            else:
                logger.error(
                    "Alerta PERDIDO — todos os canais falharam: [%s] %s em %s",
                    alert.severity, alert.rule, alert.entity,
                )
                # Undo the in-memory cooldown so the alert can retry
                # on the next cycle.
                self._undo_sent(alert)

        return delivered

    async def _send_with_retry(self, channel: Channel, alert: Alert) -> None:
        """Send an alert to a single channel with exponential backoff."""
        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                await channel.send(alert)
                return
            except Exception as exc:
                last_exc = exc
                if attempt < _RETRY_ATTEMPTS - 1:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Canal %s falhou (tentativa %d/%d), retry em %.1fs: %s",
                        channel.name, attempt + 1, _RETRY_ATTEMPTS, delay, exc,
                    )
                    await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

    async def _in_cooldown(
        self,
        session: AsyncSession,
        entity: str,
        severity: str,
        metric_type: str,
        cooldown: float,
    ) -> bool:
        cd_key = (entity, severity, metric_type)

        last = self._last_sent.get(cd_key)
        if last is not None:
            if datetime.now(timezone.utc) - last < timedelta(seconds=cooldown):
                return True

        # Fall back to the database for persistent cooldown across restarts.
        try:
            db_last = await fetch_last_notification_time(
                session, entity, severity, metric_type,
            )
            if db_last is not None:
                if db_last.tzinfo is None:
                    db_last = db_last.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - db_last < timedelta(seconds=cooldown):
                    self._last_sent[cd_key] = db_last
                    return True
        except Exception:
            logger.debug("Failed to check persistent cooldown, relying on in-memory only")

        return False

    def _mark_sent(self, entity: str, severity: str, metric_type: str) -> None:
        self._last_sent[(entity, severity, metric_type)] = datetime.now(timezone.utc)

    def _undo_sent(self, alert: Alert) -> None:
        """Remove the in-memory cooldown entry for a failed alert so it
        can be retried on the next evaluation cycle."""
        cd_key = (alert.entity, alert.severity, alert.rule)
        self._last_sent.pop(cd_key, None)


async def _consume_force_run(session: AsyncSession) -> bool:
    """Consume pending force-run commands requested from the Runs UI."""
    result = await session.execute(
        text(
            """
            UPDATE base.service_command
            SET consumed_at = NOW()
            WHERE id IN (
                SELECT id FROM base.service_command
                WHERE service = 'notifier' AND action = 'force_run' AND consumed_at IS NULL
                ORDER BY id FOR UPDATE SKIP LOCKED
            )
            RETURNING id
            """
        )
    )
    return result.first() is not None
