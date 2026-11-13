"""Remove redundant statement payloads while retaining replay fingerprints."""

import os
import time

import psycopg


def prune_receipts(batch_size: int = 2000) -> int:
    """Clear payload copies in small committed batches without deleting receipts."""
    if not 1 <= batch_size <= 10000:
        raise ValueError("Batch size must be between 1 and 10000")
    total = 0
    with psycopg.connect(
        host=os.getenv("DB_HOST", "db"), port=os.getenv("DB_PORT", "5432"),
        user=os.getenv("DB_USER", "postgres"), password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_NAME", "postgres"),
        options="-c lock_timeout=3s -c statement_timeout=30s",
    ) as connection:
        projects = connection.execute("SELECT id FROM ingestion.project ORDER BY id").fetchall()
        connection.commit()
        for project_id, in projects:
            previous = None
            while True:
                condition = "" if previous is None else "AND (received_at,source_id,event_id)<(%s,%s,%s)"
                parameters = (project_id,) + (() if previous is None else previous) + (batch_size,)
                rows = connection.execute("""
                WITH batch AS (
                    SELECT project_id,source_id,event_id FROM ingestion.event
                    WHERE project_id=%s AND table_name='metric_query_workload' AND payload<>'{}'::jsonb
                """ + condition + """
                    ORDER BY received_at DESC,source_id DESC,event_id DESC LIMIT %s
                ) UPDATE ingestion.event AS receipt SET payload='{}'::jsonb
                FROM batch WHERE (receipt.project_id,receipt.source_id,receipt.event_id)
                    =(batch.project_id,batch.source_id,batch.event_id)
                RETURNING receipt.received_at,receipt.source_id,receipt.event_id
                """, parameters).fetchall()
                connection.commit()
                if not rows:
                    break
                # UUID order scatters heap access; the existing received-time
                # index follows physical ingestion order with smaller I/O.
                previous = min(rows)
                total += len(rows)
                if total % 20000 == 0:
                    print(f"Removed {total} redundant statement payloads", flush=True)
                time.sleep(0.05)
    print(f"Receipt cleanup complete: {total}", flush=True)
    return total


if __name__ == "__main__":
    prune_receipts()
