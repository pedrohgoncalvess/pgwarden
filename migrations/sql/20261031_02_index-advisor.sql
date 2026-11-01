-- depends: 20260709_01_zo2AJ-analytics-module

ALTER TABLE metadata."index" ADD COLUMN is_valid BOOLEAN;
ALTER TABLE metric."table" ADD COLUMN n_tup_ins BIGINT;
ALTER TABLE metric."table" ADD COLUMN n_tup_upd BIGINT;
ALTER TABLE metric."table" ADD COLUMN n_tup_del BIGINT;
ALTER TABLE metric."table" ADD COLUMN n_tup_hot_upd BIGINT;
ALTER TABLE metric."table" ADD COLUMN stats_reset TIMESTAMPTZ;

CREATE TABLE metric.query_workload (
    collected_at TIMESTAMPTZ NOT NULL,
    database_id BIGINT NOT NULL REFERENCES metadata.database(id) ON DELETE CASCADE,
    query_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    is_toplevel BOOLEAN NOT NULL,
    calls BIGINT NOT NULL,
    total_exec_time DOUBLE PRECISION NOT NULL,
    shared_blks_read BIGINT NOT NULL,
    shared_blks_hit BIGINT NOT NULL,
    stats_reset TIMESTAMPTZ,
    dealloc BIGINT NOT NULL,
    PRIMARY KEY (collected_at, database_id, query_id, user_id, is_toplevel)
);
CREATE INDEX query_workload_database_time_idx ON metric.query_workload(database_id, collected_at);
