"""Optional pg_stat_statements snapshots, independent of active-query sampling."""

from datetime import datetime, timezone

from psycopg import sql
from psycopg.rows import dict_row

from database import load_storage_query
from log import logger


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
                    return 0
                schema = extension['nspname']
                await cur.execute(sql.SQL("""
                    SELECT s.queryid AS query_id, s.userid AS user_id,
                           s.toplevel AS is_toplevel, s.calls, s.total_exec_time,
                           s.shared_blks_read, s.shared_blks_hit, info.stats_reset, info.dealloc
                    FROM {}.pg_stat_statements s
                    CROSS JOIN {}.pg_stat_statements_info info
                    WHERE s.dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
                      AND s.queryid IS NOT NULL
                """).format(sql.Identifier(schema), sql.Identifier(schema)))
                rows = await cur.fetchall()
    except Exception as error:
        await logger.info('QueryWorkloadCollector', 'query_workload',
                          f'Optional workload statistics unavailable (db_id={database_id}): {error}')
        return 0
    if not rows:
        return 0
    collected_at = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    values = [dict(row, collected_at=collected_at, database_id=database_id) for row in rows]
    query = load_storage_query('metric', 'query_workload', 'INSERT', 'default')
    async with metrics_db as conn:
        async with conn.cursor() as cur:
            await cur.executemany(query, values)
        await conn.commit()
    return len(values)
