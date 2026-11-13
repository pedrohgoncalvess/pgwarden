DROP TRIGGER IF EXISTS sender_metric_query_workload_insert;
ALTER TABLE metric_query_workload RENAME TO metric_query_workload_normalized;
CREATE TABLE metric_query_workload (
    collected_at TEXT NOT NULL,
    database_id INTEGER NOT NULL REFERENCES metadata_database(id) ON DELETE CASCADE,
    query_id INTEGER NOT NULL, user_id INTEGER NOT NULL, is_toplevel INTEGER NOT NULL,
    calls INTEGER NOT NULL, total_exec_time REAL NOT NULL,
    shared_blks_read INTEGER NOT NULL, shared_blks_hit INTEGER NOT NULL,
    stats_reset TEXT, dealloc INTEGER NOT NULL,
    query TEXT, query_hash TEXT, user_name TEXT, statement_data TEXT,
    PRIMARY KEY(collected_at,database_id,query_id,user_id,is_toplevel)
);
INSERT INTO metric_query_workload
SELECT sample.collected_at,sample.database_id,sample.query_id,sample.user_id,sample.is_toplevel,sample.calls,sample.total_exec_time,sample.shared_blks_read,sample.shared_blks_hit,sample.stats_reset,sample.dealloc,sql_text.query,sql_text.query_hash,sample.user_name,
    json_object('queryid',sample.query_id,'userid',sample.user_id,'dbid',sample.source_database_oid,'toplevel',sample.is_toplevel,'query',sql_text.query,'plans',sample."plans",'rows',sample."rows",'shared_blks_dirtied',sample."shared_blks_dirtied",'shared_blks_written',sample."shared_blks_written",'local_blks_hit',sample."local_blks_hit",'local_blks_read',sample."local_blks_read",'local_blks_dirtied',sample."local_blks_dirtied",'local_blks_written',sample."local_blks_written",'temp_blks_read',sample."temp_blks_read",'temp_blks_written',sample."temp_blks_written",'wal_records',sample."wal_records",'wal_fpi',sample."wal_fpi",'wal_buffers_full',sample."wal_buffers_full",'jit_functions',sample."jit_functions",'jit_inlining_count',sample."jit_inlining_count",'jit_optimization_count',sample."jit_optimization_count",'jit_emission_count',sample."jit_emission_count",'jit_deform_count',sample."jit_deform_count",'parallel_workers_to_launch',sample."parallel_workers_to_launch",'parallel_workers_launched',sample."parallel_workers_launched",'total_plan_time',sample."total_plan_time",'min_plan_time',sample."min_plan_time",'max_plan_time',sample."max_plan_time",'mean_plan_time',sample."mean_plan_time",'stddev_plan_time',sample."stddev_plan_time",'min_exec_time',sample."min_exec_time",'max_exec_time',sample."max_exec_time",'mean_exec_time',sample."mean_exec_time",'stddev_exec_time',sample."stddev_exec_time",'blk_read_time',sample."blk_read_time",'blk_write_time',sample."blk_write_time",'shared_blk_read_time',sample."shared_blk_read_time",'shared_blk_write_time',sample."shared_blk_write_time",'local_blk_read_time',sample."local_blk_read_time",'local_blk_write_time',sample."local_blk_write_time",'temp_blk_read_time',sample."temp_blk_read_time",'temp_blk_write_time',sample."temp_blk_write_time",'jit_generation_time',sample."jit_generation_time",'jit_inlining_time',sample."jit_inlining_time",'jit_optimization_time',sample."jit_optimization_time",'jit_emission_time',sample."jit_emission_time",'jit_deform_time',sample."jit_deform_time",'stats_since',sample."stats_since",'minmax_stats_since',sample."minmax_stats_since",'wal_bytes',sample."wal_bytes")
FROM metric_query_workload_normalized sample
LEFT JOIN metric_statement_text sql_text ON sql_text.id=sample.statement_text_id;
DROP TABLE metric_query_workload_normalized;
DROP TABLE metric_statement_text;
CREATE INDEX query_workload_database_time_idx ON metric_query_workload(database_id,collected_at);
CREATE INDEX query_workload_identity_idx ON metric_query_workload(database_id,query_id,collected_at DESC);
CREATE INDEX query_workload_hash_idx ON metric_query_workload(database_id,query_hash,collected_at DESC);
