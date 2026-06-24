-- depends: 20260425_02_docs-tags-history

CREATE TABLE metric.database_stat (
    collected_at      TIMESTAMPTZ NOT NULL,
    database_id       BIGINT NOT NULL REFERENCES metadata.database(id) ON DELETE CASCADE,
    xact_commit       BIGINT,
    xact_rollback     BIGINT,
    blks_read         BIGINT,
    blks_hit          BIGINT,
    tup_returned      BIGINT,
    tup_fetched       BIGINT,
    tup_inserted      BIGINT,
    tup_updated       BIGINT,
    tup_deleted       BIGINT,
    conflicts         BIGINT,
    deadlocks         BIGINT,
    db_size_bytes     BIGINT,
    CONSTRAINT database_stat_pk PRIMARY KEY (collected_at, database_id)
);

SELECT create_hypertable('metric.database_stat', 'collected_at');

COMMENT ON TABLE metric.database_stat IS 'pg_stat_database snapshot. Used to derive TPS, cache hit ratio, and database size over time.';
COMMENT ON COLUMN metric.database_stat.xact_commit IS 'Cumulative committed transactions since server start.';
COMMENT ON COLUMN metric.database_stat.xact_rollback IS 'Cumulative rolled-back transactions since server start.';
COMMENT ON COLUMN metric.database_stat.blks_read IS 'Disk blocks read (cache misses).';
COMMENT ON COLUMN metric.database_stat.blks_hit IS 'Buffer cache hits.';
COMMENT ON COLUMN metric.database_stat.deadlocks IS 'Number of deadlocks detected.';
COMMENT ON COLUMN metric.database_stat.db_size_bytes IS 'Total database size in bytes from pg_database_size().';
