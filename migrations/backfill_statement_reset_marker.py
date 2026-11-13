"""Backfill statement reset markers online after applying their migration."""

import os
import time

import psycopg


def backfill_markers(batch_size: int = 2000) -> int:
    """Commit small chronological batches without locking the entire table."""
    total = 0
    previous = None
    with psycopg.connect(
        host=os.getenv("DB_HOST", "db"), port=os.getenv("DB_PORT", "5432"),
        user=os.getenv("DB_USER", "postgres"), password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_NAME", "postgres"),
        options="-c lock_timeout=3s -c statement_timeout=30s",
    ) as connection:
        while True:
            condition = "" if previous is None else """AND
                (collected_at,database_id,query_id,user_id,is_toplevel) > (%s,%s,%s,%s,%s)"""
            parameters = (() if previous is None else previous) + (batch_size,)
            rows = connection.execute("""
                WITH batch AS (
                    SELECT collected_at,database_id,query_id,user_id,is_toplevel
                    FROM metric.query_workload WHERE statement_stats_since IS NULL
                """ + condition + """
                    ORDER BY collected_at,database_id,query_id,user_id,is_toplevel LIMIT %s
                )
                UPDATE metric.query_workload AS workload
                SET statement_stats_since=COALESCE((statement_data::json -> 'stats_since')::text,'null')
                FROM batch WHERE
                    (workload.collected_at,workload.database_id,workload.query_id,workload.user_id,workload.is_toplevel)
                    = (batch.collected_at,batch.database_id,batch.query_id,batch.user_id,batch.is_toplevel)
                RETURNING workload.collected_at,workload.database_id,workload.query_id,workload.user_id,workload.is_toplevel
            """, parameters).fetchall()
            connection.commit()
            if not rows:
                break
            previous = max(rows)
            total += len(rows)
            if total % 20000 == 0:
                print(f"Backfilled {total} snapshots", flush=True)
            time.sleep(0.05)
    print(f"Backfill complete: {total} snapshots", flush=True)
    return total


if __name__ == "__main__":
    backfill_markers()
