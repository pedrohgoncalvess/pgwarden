-- depends: 20261030_06_sqlite-history

ALTER TABLE metadata_index ADD COLUMN is_valid BOOLEAN;
ALTER TABLE metric_table ADD COLUMN n_tup_ins INTEGER;
ALTER TABLE metric_table ADD COLUMN n_tup_upd INTEGER;
ALTER TABLE metric_table ADD COLUMN n_tup_del INTEGER;
ALTER TABLE metric_table ADD COLUMN n_tup_hot_upd INTEGER;
ALTER TABLE metric_table ADD COLUMN stats_reset TEXT;

CREATE TABLE metric_query_workload (
    collected_at TEXT NOT NULL,
    database_id INTEGER NOT NULL REFERENCES metadata_database(id) ON DELETE CASCADE,
    query_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    is_toplevel BOOLEAN NOT NULL,
    calls INTEGER NOT NULL,
    total_exec_time REAL NOT NULL,
    shared_blks_read INTEGER NOT NULL,
    shared_blks_hit INTEGER NOT NULL,
    stats_reset TEXT,
    dealloc INTEGER NOT NULL,
    PRIMARY KEY (collected_at, database_id, query_id, user_id, is_toplevel)
);
CREATE INDEX query_workload_database_time_idx ON metric_query_workload(database_id, collected_at);
