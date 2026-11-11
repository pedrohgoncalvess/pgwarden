"""Windowed evidence for index decisions. Counters are never treated as rates."""

import os

from sqlalchemy import text


WINDOW_DAYS = max(1, min(int(os.getenv("INDEX_ADVISOR_WINDOW_DAYS", "7")), 30))
WRITE_HEAVY_PER_SECOND = float(os.getenv("INDEX_ADVISOR_WRITE_HEAVY_PER_SECOND", "10"))


async def table_evidence(session, database_id: int) -> dict[int, dict]:
    result = await session.execute(text("""
        WITH samples AS (
            SELECT m.*, lag(collected_at) OVER w AS previous_at,
                   lag(n_tup_ins) OVER w AS prev_ins, lag(n_tup_upd) OVER w AS prev_upd,
                   lag(n_tup_del) OVER w AS prev_del, lag(stats_reset) OVER w AS prev_reset,
                   lag(n_tup_hot_upd) OVER w AS prev_hot
            FROM metric.table m JOIN metadata.table t ON t.id = m.table_id
            WHERE t.database_id = :database_id AND t.deleted_at IS NULL
              AND m.collected_at >= NOW() - make_interval(days => :days)
            WINDOW w AS (PARTITION BY table_id ORDER BY collected_at)
        ), writes AS (
            SELECT table_id,
                   SUM(n_tup_ins-prev_ins + n_tup_upd-prev_upd + n_tup_del-prev_del) AS writes,
                   SUM(EXTRACT(EPOCH FROM collected_at-previous_at)) AS seconds,
                   SUM(n_tup_upd-prev_upd) AS updates,
                   SUM(n_tup_hot_upd-prev_hot) AS hot_updates
            FROM samples WHERE previous_at IS NOT NULL
              AND stats_reset IS NOT DISTINCT FROM prev_reset
              AND n_tup_ins >= prev_ins AND n_tup_upd >= prev_upd AND n_tup_del >= prev_del
              AND n_tup_hot_upd >= prev_hot
            GROUP BY table_id
            HAVING MAX(collected_at) >= NOW() - INTERVAL '1 day'
        ), sizes AS (
            SELECT DISTINCT ON (i.id) i.id, i.table_id, m.size
            FROM metadata.index i LEFT JOIN metric.index m ON m.index_id = i.id
            WHERE i.database_id = :database_id AND i.deleted_at IS NULL
            ORDER BY i.id, m.collected_at DESC
        )
        SELECT t.id AS table_id, w.writes, w.seconds, w.updates, w.hot_updates,
               COUNT(s.id) AS index_count, SUM(s.size) AS index_size_bytes
        FROM metadata.table t LEFT JOIN writes w ON w.table_id = t.id
        LEFT JOIN sizes s ON s.table_id = t.id
        WHERE t.database_id = :database_id AND t.deleted_at IS NULL
        GROUP BY t.id, w.writes, w.seconds, w.updates, w.hot_updates
    """), {"database_id": database_id, "days": WINDOW_DAYS})
    evidence = {}
    for row in result.mappings():
        seconds = float(row.seconds or 0)
        rate = float(row.writes) / seconds if seconds >= 3600 and row.writes is not None else None
        evidence[row.table_id] = {
            "write_operations": int(row.writes) if row.writes is not None else None,
            "write_observation_seconds": seconds,
            "hot_update_fraction": round(float(row.hot_updates) / float(row.updates), 4) if row.updates else None,
            "writes_per_second": round(rate, 3) if rate is not None else None,
            "write_heavy": rate >= WRITE_HEAVY_PER_SECOND if rate is not None else None,
            "write_heavy_threshold_per_second": WRITE_HEAVY_PER_SECOND,
            "index_count": row.index_count,
            "index_size_bytes": row.index_size_bytes,
        }
    return evidence


async def query_evidence(session, database_id: int) -> dict[int, dict]:
    result = await session.execute(text("""
        WITH samples AS (
            SELECT m.*, lag(calls) OVER w AS prev_calls,
                lag(total_exec_time) OVER w AS prev_time,
                lag(shared_blks_read) OVER w AS prev_read,
                lag(shared_blks_hit) OVER w AS prev_hit,
                lag(stats_reset) OVER w AS prev_reset,
                lag(dealloc) OVER w AS prev_dealloc,
                lag(statement_data) OVER w AS prev_statement_data,
                lag(collected_at) OVER w AS previous_at
            FROM metric.query_workload m
            WHERE database_id = :database_id
              AND collected_at >= NOW() - make_interval(days => :days)
            WINDOW w AS (PARTITION BY query_id, user_id, is_toplevel ORDER BY collected_at)
        )
        SELECT query_id, SUM(calls-prev_calls) AS calls,
            SUM(total_exec_time-prev_time) AS total_exec_time_ms,
            SUM(shared_blks_read-prev_read) AS shared_blks_read,
            SUM(shared_blks_hit-prev_hit) AS shared_blks_hit,
            MIN(previous_at) AS first_seen_at, MAX(collected_at) AS last_seen_at
        FROM samples WHERE is_toplevel AND previous_at IS NOT NULL
          AND stats_reset IS NOT DISTINCT FROM prev_reset
          AND dealloc = prev_dealloc
          AND (statement_data::jsonb ->> 'stats_since') IS NOT DISTINCT FROM (prev_statement_data::jsonb ->> 'stats_since')
          AND calls >= prev_calls AND total_exec_time >= prev_time
          AND shared_blks_read >= prev_read AND shared_blks_hit >= prev_hit
        GROUP BY query_id
    """), {"database_id": database_id, "days": WINDOW_DAYS})
    return {row.query_id: dict(row) for row in result.mappings()}
