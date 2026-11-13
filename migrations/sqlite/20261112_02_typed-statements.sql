-- depends: 20261102_01_workload-auto-disable

PRAGMA secure_delete=OFF;
PRAGMA cache_size=-8192;
CREATE TEMP TABLE typed_statement_fields_check(valid INTEGER CHECK(valid=1));
INSERT INTO typed_statement_fields_check SELECT NOT EXISTS (
    SELECT 1 FROM metric_query_workload AS sample,json_each(sample.statement_data) AS field
    WHERE field.key NOT IN ('blk_read_time','blk_write_time','calls','dbid','jit_deform_count','jit_deform_time','jit_emission_count','jit_emission_time','jit_functions','jit_generation_time','jit_inlining_count','jit_inlining_time','jit_optimization_count','jit_optimization_time','local_blk_read_time','local_blk_write_time','local_blks_dirtied','local_blks_hit','local_blks_read','local_blks_written','max_exec_time','max_plan_time','mean_exec_time','mean_plan_time','min_exec_time','min_plan_time','minmax_stats_since','parallel_workers_launched','parallel_workers_to_launch','plans','query','queryid','rows','shared_blk_read_time','shared_blk_write_time','shared_blks_dirtied','shared_blks_hit','shared_blks_read','shared_blks_written','source_database_oid','stats_since','stddev_exec_time','stddev_plan_time','temp_blk_read_time','temp_blk_write_time','temp_blks_read','temp_blks_written','toplevel','total_exec_time','total_plan_time','userid','wal_buffers_full','wal_bytes','wal_fpi','wal_records')
);
DROP TABLE typed_statement_fields_check;
DROP TRIGGER IF EXISTS sender_metric_query_workload_insert;
CREATE TABLE metric_statement_text (
    id INTEGER PRIMARY KEY,
    database_id INTEGER NOT NULL REFERENCES metadata_database(id) ON DELETE CASCADE,
    fingerprint TEXT,
    query TEXT NOT NULL,
    query_hash TEXT,
    UNIQUE(database_id,query)
);
INSERT OR IGNORE INTO metric_statement_text(database_id,fingerprint,query,query_hash)
SELECT database_id,query_hash,query,query_hash
FROM metric_query_workload WHERE query IS NOT NULL;
CREATE TABLE metric_query_workload_typed (
    "collected_at" TEXT NOT NULL,
    "database_id" INTEGER NOT NULL REFERENCES metadata_database(id) ON DELETE CASCADE,
    "query_id" INTEGER NOT NULL,
    "user_id" INTEGER NOT NULL,
    "is_toplevel" INTEGER NOT NULL,
    "calls" INTEGER NOT NULL,
    "total_exec_time" REAL NOT NULL,
    "shared_blks_read" INTEGER NOT NULL,
    "shared_blks_hit" INTEGER NOT NULL,
    "stats_reset" TEXT,
    "dealloc" INTEGER NOT NULL,
    "user_name" TEXT,
    "statement_text_id" INTEGER REFERENCES metric_statement_text(id),
    "plans" INTEGER,
    "rows" INTEGER,
    "shared_blks_dirtied" INTEGER,
    "shared_blks_written" INTEGER,
    "local_blks_hit" INTEGER,
    "local_blks_read" INTEGER,
    "local_blks_dirtied" INTEGER,
    "local_blks_written" INTEGER,
    "temp_blks_read" INTEGER,
    "temp_blks_written" INTEGER,
    "wal_records" INTEGER,
    "wal_fpi" INTEGER,
    "wal_buffers_full" INTEGER,
    "jit_functions" INTEGER,
    "jit_inlining_count" INTEGER,
    "jit_optimization_count" INTEGER,
    "jit_emission_count" INTEGER,
    "jit_deform_count" INTEGER,
    "parallel_workers_to_launch" INTEGER,
    "parallel_workers_launched" INTEGER,
    "total_plan_time" REAL,
    "min_plan_time" REAL,
    "max_plan_time" REAL,
    "mean_plan_time" REAL,
    "stddev_plan_time" REAL,
    "min_exec_time" REAL,
    "max_exec_time" REAL,
    "mean_exec_time" REAL,
    "stddev_exec_time" REAL,
    "blk_read_time" REAL,
    "blk_write_time" REAL,
    "shared_blk_read_time" REAL,
    "shared_blk_write_time" REAL,
    "local_blk_read_time" REAL,
    "local_blk_write_time" REAL,
    "temp_blk_read_time" REAL,
    "temp_blk_write_time" REAL,
    "jit_generation_time" REAL,
    "jit_inlining_time" REAL,
    "jit_optimization_time" REAL,
    "jit_emission_time" REAL,
    "jit_deform_time" REAL,
    "stats_since" TEXT,
    "minmax_stats_since" TEXT,
    "wal_bytes" TEXT,
    "source_database_oid" INTEGER,
    PRIMARY KEY(collected_at,database_id,query_id,user_id,is_toplevel)
);
INSERT INTO metric_query_workload_typed
SELECT old."collected_at",
       old."database_id",
       old."query_id",
       old."user_id",
       old."is_toplevel",
       old."calls",
       old."total_exec_time",
       old."shared_blks_read",
       old."shared_blks_hit",
       old."stats_reset",
       old."dealloc",
       old."user_name",
       sql_text.id,
       json_extract(old.statement_data,'$.plans'),
       json_extract(old.statement_data,'$.rows'),
       json_extract(old.statement_data,'$.shared_blks_dirtied'),
       json_extract(old.statement_data,'$.shared_blks_written'),
       json_extract(old.statement_data,'$.local_blks_hit'),
       json_extract(old.statement_data,'$.local_blks_read'),
       json_extract(old.statement_data,'$.local_blks_dirtied'),
       json_extract(old.statement_data,'$.local_blks_written'),
       json_extract(old.statement_data,'$.temp_blks_read'),
       json_extract(old.statement_data,'$.temp_blks_written'),
       json_extract(old.statement_data,'$.wal_records'),
       json_extract(old.statement_data,'$.wal_fpi'),
       json_extract(old.statement_data,'$.wal_buffers_full'),
       json_extract(old.statement_data,'$.jit_functions'),
       json_extract(old.statement_data,'$.jit_inlining_count'),
       json_extract(old.statement_data,'$.jit_optimization_count'),
       json_extract(old.statement_data,'$.jit_emission_count'),
       json_extract(old.statement_data,'$.jit_deform_count'),
       json_extract(old.statement_data,'$.parallel_workers_to_launch'),
       json_extract(old.statement_data,'$.parallel_workers_launched'),
       json_extract(old.statement_data,'$.total_plan_time'),
       json_extract(old.statement_data,'$.min_plan_time'),
       json_extract(old.statement_data,'$.max_plan_time'),
       json_extract(old.statement_data,'$.mean_plan_time'),
       json_extract(old.statement_data,'$.stddev_plan_time'),
       json_extract(old.statement_data,'$.min_exec_time'),
       json_extract(old.statement_data,'$.max_exec_time'),
       json_extract(old.statement_data,'$.mean_exec_time'),
       json_extract(old.statement_data,'$.stddev_exec_time'),
       json_extract(old.statement_data,'$.blk_read_time'),
       json_extract(old.statement_data,'$.blk_write_time'),
       json_extract(old.statement_data,'$.shared_blk_read_time'),
       json_extract(old.statement_data,'$.shared_blk_write_time'),
       json_extract(old.statement_data,'$.local_blk_read_time'),
       json_extract(old.statement_data,'$.local_blk_write_time'),
       json_extract(old.statement_data,'$.temp_blk_read_time'),
       json_extract(old.statement_data,'$.temp_blk_write_time'),
       json_extract(old.statement_data,'$.jit_generation_time'),
       json_extract(old.statement_data,'$.jit_inlining_time'),
       json_extract(old.statement_data,'$.jit_optimization_time'),
       json_extract(old.statement_data,'$.jit_emission_time'),
       json_extract(old.statement_data,'$.jit_deform_time'),
       json_extract(old.statement_data,'$.stats_since'),
       json_extract(old.statement_data,'$.minmax_stats_since'),
       CASE WHEN json_type(old.statement_data,'$.wal_bytes') IN ('integer','real','text')
            THEN trim(old.statement_data -> '$.wal_bytes','"') END,
       json_extract(old.statement_data,'$.dbid')
FROM metric_query_workload AS old
LEFT JOIN metric_statement_text AS sql_text ON sql_text.database_id=old.database_id AND sql_text.query=old.query;
CREATE TEMP TABLE typed_statement_migration_check(valid INTEGER CHECK(valid=1));
INSERT INTO typed_statement_migration_check
SELECT (SELECT count(*) FROM metric_query_workload_typed) = (SELECT count(*) FROM metric_query_workload);
DROP TABLE typed_statement_migration_check;
DROP TABLE metric_query_workload;
ALTER TABLE metric_query_workload_typed RENAME TO metric_query_workload;
CREATE INDEX query_workload_database_time_idx ON metric_query_workload(database_id,collected_at);
CREATE INDEX query_workload_identity_idx ON metric_query_workload(database_id,query_id,collected_at DESC);
CREATE INDEX query_workload_window_idx ON metric_query_workload(database_id,query_id,user_id,is_toplevel,collected_at);
