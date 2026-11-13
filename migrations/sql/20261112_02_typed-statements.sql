-- depends: 20261112_01_statement-reset-marker

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM metric.query_workload AS sample,
        LATERAL jsonb_object_keys(COALESCE(sample.statement_data::jsonb,'{}'::jsonb)) AS field(name)
        WHERE field.name NOT IN ('blk_read_time','blk_write_time','calls','dbid','jit_deform_count','jit_deform_time','jit_emission_count','jit_emission_time','jit_functions','jit_generation_time','jit_inlining_count','jit_inlining_time','jit_optimization_count','jit_optimization_time','local_blk_read_time','local_blk_write_time','local_blks_dirtied','local_blks_hit','local_blks_read','local_blks_written','max_exec_time','max_plan_time','mean_exec_time','mean_plan_time','min_exec_time','min_plan_time','minmax_stats_since','parallel_workers_launched','parallel_workers_to_launch','plans','query','queryid','rows','shared_blk_read_time','shared_blk_write_time','shared_blks_dirtied','shared_blks_hit','shared_blks_read','shared_blks_written','source_database_oid','stats_since','stddev_exec_time','stddev_plan_time','temp_blk_read_time','temp_blk_write_time','temp_blks_read','temp_blks_written','toplevel','total_exec_time','total_plan_time','userid','wal_buffers_full','wal_bytes','wal_fpi','wal_records'))
    THEN RAISE EXCEPTION 'Unknown statement fields; extend typed schema before migration'; END IF;
END $$;

CREATE TABLE metric.statement_text (
    id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL REFERENCES metadata.database(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    query TEXT NOT NULL,
    query_hash TEXT,
    UNIQUE(database_id,fingerprint)
);
INSERT INTO metric.statement_text(database_id,fingerprint,query,query_hash)
SELECT database_id,encode(sha256(convert_to(query,'UTF8')),'hex'),query,md5(query)
FROM (SELECT DISTINCT database_id,query FROM metric.query_workload WHERE query IS NOT NULL) AS texts;

CREATE TABLE metric.query_workload_typed (
    "collected_at" TIMESTAMPTZ NOT NULL,
    "database_id" BIGINT NOT NULL REFERENCES metadata.database(id) ON DELETE CASCADE,
    "query_id" BIGINT NOT NULL,
    "user_id" BIGINT NOT NULL,
    "is_toplevel" BOOLEAN NOT NULL,
    "calls" BIGINT NOT NULL,
    "total_exec_time" DOUBLE PRECISION NOT NULL,
    "shared_blks_read" BIGINT NOT NULL,
    "shared_blks_hit" BIGINT NOT NULL,
    "stats_reset" TIMESTAMPTZ,
    "dealloc" BIGINT NOT NULL,
    "user_name" TEXT,
    "statement_text_id" BIGINT REFERENCES metric.statement_text(id),
    "plans" BIGINT,
    "rows" BIGINT,
    "shared_blks_dirtied" BIGINT,
    "shared_blks_written" BIGINT,
    "local_blks_hit" BIGINT,
    "local_blks_read" BIGINT,
    "local_blks_dirtied" BIGINT,
    "local_blks_written" BIGINT,
    "temp_blks_read" BIGINT,
    "temp_blks_written" BIGINT,
    "wal_records" BIGINT,
    "wal_fpi" BIGINT,
    "wal_buffers_full" BIGINT,
    "jit_functions" BIGINT,
    "jit_inlining_count" BIGINT,
    "jit_optimization_count" BIGINT,
    "jit_emission_count" BIGINT,
    "jit_deform_count" BIGINT,
    "parallel_workers_to_launch" BIGINT,
    "parallel_workers_launched" BIGINT,
    "total_plan_time" DOUBLE PRECISION,
    "min_plan_time" DOUBLE PRECISION,
    "max_plan_time" DOUBLE PRECISION,
    "mean_plan_time" DOUBLE PRECISION,
    "stddev_plan_time" DOUBLE PRECISION,
    "min_exec_time" DOUBLE PRECISION,
    "max_exec_time" DOUBLE PRECISION,
    "mean_exec_time" DOUBLE PRECISION,
    "stddev_exec_time" DOUBLE PRECISION,
    "blk_read_time" DOUBLE PRECISION,
    "blk_write_time" DOUBLE PRECISION,
    "shared_blk_read_time" DOUBLE PRECISION,
    "shared_blk_write_time" DOUBLE PRECISION,
    "local_blk_read_time" DOUBLE PRECISION,
    "local_blk_write_time" DOUBLE PRECISION,
    "temp_blk_read_time" DOUBLE PRECISION,
    "temp_blk_write_time" DOUBLE PRECISION,
    "jit_generation_time" DOUBLE PRECISION,
    "jit_inlining_time" DOUBLE PRECISION,
    "jit_optimization_time" DOUBLE PRECISION,
    "jit_emission_time" DOUBLE PRECISION,
    "jit_deform_time" DOUBLE PRECISION,
    "stats_since" TIMESTAMPTZ,
    "minmax_stats_since" TIMESTAMPTZ,
    "wal_bytes" NUMERIC(30,0),
    "source_database_oid" BIGINT,
    PRIMARY KEY(collected_at,database_id,query_id,user_id,is_toplevel)
);
INSERT INTO metric.query_workload_typed
SELECT converted.*
FROM metric.query_workload AS old
LEFT JOIN metric.statement_text AS sql_text
    ON sql_text.database_id=old.database_id AND sql_text.query_hash=md5(old.query)
    AND sql_text.query=old.query
CROSS JOIN LATERAL jsonb_populate_record(NULL::metric.query_workload_typed,
    COALESCE(old.statement_data::jsonb,'{}'::jsonb) || jsonb_build_object(
        'collected_at',old."collected_at",
        'database_id',old."database_id",
        'query_id',old."query_id",
        'user_id',old."user_id",
        'is_toplevel',old."is_toplevel",
        'calls',old."calls",
        'total_exec_time',old."total_exec_time",
        'shared_blks_read',old."shared_blks_read",
        'shared_blks_hit',old."shared_blks_hit",
        'stats_reset',old."stats_reset",
        'dealloc',old."dealloc",
        'user_name',old."user_name",
        'statement_text_id',sql_text.id,
        'source_database_oid',old.statement_data::jsonb -> 'dbid'
    )) AS converted;

DO $$ BEGIN
    IF (SELECT count(*) FROM metric.query_workload_typed) <> (SELECT count(*) FROM metric.query_workload)
    THEN RAISE EXCEPTION 'Statement snapshot count mismatch'; END IF;
END $$;
DROP TABLE metric.query_workload;
DROP FUNCTION metric.set_statement_reset_marker();
ALTER TABLE metric.query_workload_typed RENAME TO query_workload;
CREATE INDEX query_workload_database_time_idx ON metric.query_workload(database_id,collected_at);
CREATE INDEX query_workload_identity_idx ON metric.query_workload(database_id,query_id,collected_at DESC);
CREATE INDEX query_workload_window_idx ON metric.query_workload(database_id,query_id,user_id,is_toplevel,collected_at);
CREATE INDEX query_workload_text_idx ON metric.query_workload(statement_text_id,collected_at DESC);
