"""Optional pg_stat_statements snapshots, independent of active-query sampling."""

from datetime import datetime, timezone

from psycopg import sql
from psycopg.rows import dict_row

from database import load_storage_query
from database.statements import prepare_statement
from log import logger
from collector.collectors.base import BaseCollector
from collector.collectors.result import SyncResult


class StatementSourceUnavailable(RuntimeError):
    """The optional extension or one of its views is absent/unusable."""


class QueryWorkloadMetricCollector(BaseCollector):
    """Scheduled independently of activity sampling, including when it is paused."""

    def __init__(self, monitored_db, metrics_db, db_id: int) -> None:
        super().__init__(monitored_db, metrics_db)
        self._db_id = db_id

    async def _collect(self) -> SyncResult:
        try:
            inserted = await collect_query_workload(self.monitored_db, self.metrics_db, self._db_id)
        except StatementSourceUnavailable as error:
            query = load_storage_query('collector', 'config_database', 'UPDATE', 'workload_unavailable')
            async with self.metrics_db as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(query, {'database_id': self._db_id})
                    state = await cur.fetchone()
                await conn.commit()
            warning = state['warning'] if state else None
            if warning:
                await logger.warn('QueryWorkloadCollector', 'auto_disabled', f'(db_id={self._db_id}): {warning}')
            raise StatementSourceUnavailable(warning or str(error)) from error
        except Exception:
            await self._reset_failures(clear_warning=False)
            raise
        await self._reset_failures()
        return SyncResult(inserted=inserted)

    async def collect(self) -> None:
        # Unlike BaseCollector's best-effort wrapper, propagate failures to the
        # scheduler so missing statements is recorded as an errored run.
        await self._collect()

    async def _reset_failures(self, clear_warning: bool = True) -> None:
        query = load_storage_query('collector', 'config_database', 'UPDATE', 'workload_reset')
        async with self.metrics_db as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, {'database_id': self._db_id, 'clear_warning': clear_warning})
            await conn.commit()


async def collect_query_workload(monitored_db, metrics_db, database_id: int) -> int:
    # Discover the extension schema instead of relying on the role's search_path.
    # Missing privileges/extension must not interrupt ordinary metric collection.
    try:
        async with monitored_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("""
                    SELECT n.nspname FROM pg_extension e
                    JOIN pg_namespace n ON n.oid = e.extnamespace
                    WHERE e.extname = 'pg_stat_statements'
                """)
                extension = await cur.fetchone()
                if not extension:
                    raise StatementSourceUnavailable('pg_stat_statements extension is not installed in the monitored database.')
                schema = extension['nspname']
                await cur.execute(sql.SQL("""
                    SELECT s.*, info.stats_reset, info.dealloc, r.rolname AS user_name
                    FROM {}.pg_stat_statements s
                    CROSS JOIN {}.pg_stat_statements_info info
                    LEFT JOIN pg_roles r ON r.oid = s.userid
                    WHERE s.dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
                      AND s.queryid IS NOT NULL
                      AND s.queryid <> 0
                """).format(sql.Identifier(schema), sql.Identifier(schema)))
                rows = await cur.fetchall()
    except Exception as error:
        if isinstance(error, StatementSourceUnavailable):
            raise
        if getattr(error, 'sqlstate', None) == '42P01' or (
            getattr(error, 'sqlstate', None) == '55000' and 'pg_stat_statements' in str(error)
        ):
            raise StatementSourceUnavailable(str(error)) from error
        raise
    if not rows:
        return 0
    collected_at = datetime.now(timezone.utc)
    values = [prepare_statement(row, database_id, collected_at) for row in rows]
    query = load_storage_query('metric', 'query_workload', 'INSERT', 'default')
    text_query = load_storage_query('metric', 'query_workload', 'INSERT', 'texts')
    async with metrics_db as conn:
        async with conn.cursor() as cur:
            texts = {row['fingerprint']: row for row in values if row['query'] is not None}
            await cur.executemany(text_query, list(texts.values()))
            await cur.executemany(query, values)
        await conn.commit()
    return len(values)
