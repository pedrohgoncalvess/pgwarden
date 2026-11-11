"""Read retention metadata without scanning metric histories."""

from sqlalchemy import text


TABLES = text("""
    SELECT h.hypertable_name AS name, j.job_id,
           j.config->>'drop_after' AS retention_interval,
           j.scheduled, j.schedule_interval::text AS schedule_interval,
           s.next_start, s.last_run_status,
           EXTRACT(EPOCH FROM (now() - (now() -
               CAST(j.config->>'drop_after' AS interval)))) AS retention_seconds
    FROM timescaledb_information.hypertables h
    JOIN timescaledb_information.dimensions d
      ON d.hypertable_schema = h.hypertable_schema
     AND d.hypertable_name = h.hypertable_name
     AND d.column_name = 'collected_at'
     AND d.time_interval IS NOT NULL
    LEFT JOIN timescaledb_information.jobs j
      ON j.hypertable_schema = h.hypertable_schema
     AND j.hypertable_name = h.hypertable_name
     AND j.proc_name = 'policy_retention'
    LEFT JOIN timescaledb_information.job_stats s ON s.job_id = j.job_id
    WHERE h.hypertable_schema = 'metric'
    ORDER BY h.hypertable_name
""")

CHUNKS = text("""
    SELECT c.range_start, c.range_end, c.is_compressed,
           COALESCE(z.total_bytes, 0) AS total_bytes
    FROM timescaledb_information.chunks c
    LEFT JOIN chunks_detailed_size(CAST(:relation AS regclass)) z
      ON z.chunk_schema = c.chunk_schema AND z.chunk_name = c.chunk_name
    WHERE c.hypertable_schema = 'metric' AND c.hypertable_name = :name
    ORDER BY c.range_start
""")

WINDOW = text("""
    SELECT now() AS measured_at, now() - CAST(CAST(:interval AS text) AS interval) AS cutoff,
           EXTRACT(EPOCH FROM (now() -
               (now() - CAST(CAST(:interval AS text) AS interval)))) AS seconds
""")
