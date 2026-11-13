ALTER TABLE metric.query_workload RENAME TO query_workload_normalized;
CREATE TABLE metric.query_workload (
    collected_at TIMESTAMPTZ NOT NULL,
    database_id BIGINT NOT NULL REFERENCES metadata.database(id) ON DELETE CASCADE,
    query_id BIGINT NOT NULL, user_id BIGINT NOT NULL, is_toplevel BOOLEAN NOT NULL,
    calls BIGINT NOT NULL, total_exec_time DOUBLE PRECISION NOT NULL,
    shared_blks_read BIGINT NOT NULL, shared_blks_hit BIGINT NOT NULL,
    stats_reset TIMESTAMPTZ, dealloc BIGINT NOT NULL,
    query TEXT, query_hash TEXT, user_name TEXT, statement_data TEXT,
    PRIMARY KEY(collected_at,database_id,query_id,user_id,is_toplevel)
);
INSERT INTO metric.query_workload
SELECT sample.collected_at,sample.database_id,sample.query_id,sample.user_id,sample.is_toplevel,sample.calls,sample.total_exec_time,sample.shared_blks_read,sample.shared_blks_hit,sample.stats_reset,sample.dealloc,sql_text.query,sql_text.query_hash,sample.user_name,
    (jsonb_strip_nulls(to_jsonb(sample) - ARRAY['collected_at','database_id','query_id','user_id','is_toplevel','statement_text_id','source_database_oid','user_name','stats_reset','dealloc'])
     || jsonb_build_object('queryid',sample.query_id,'userid',sample.user_id,
                          'dbid',sample.source_database_oid,'toplevel',sample.is_toplevel,'query',sql_text.query))::text
FROM metric.query_workload_normalized sample
LEFT JOIN metric.statement_text sql_text ON sql_text.id=sample.statement_text_id;
DROP TABLE metric.query_workload_normalized;
DROP TABLE metric.statement_text;
CREATE INDEX query_workload_database_time_idx ON metric.query_workload(database_id,collected_at);
CREATE INDEX query_workload_identity_idx ON metric.query_workload(database_id,query_id,collected_at DESC);
CREATE INDEX query_workload_hash_idx ON metric.query_workload(database_id,query_hash,collected_at DESC);

ALTER TABLE metric.query_workload
    ADD COLUMN IF NOT EXISTS statement_stats_since TEXT;

CREATE FUNCTION metric.set_statement_reset_marker() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.statement_stats_since := COALESCE(
        (NEW.statement_data::json -> 'stats_since')::text, 'null'
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER statement_reset_marker
    BEFORE INSERT OR UPDATE OF statement_data ON metric.query_workload
    FOR EACH ROW EXECUTE FUNCTION metric.set_statement_reset_marker();

CREATE INDEX IF NOT EXISTS query_workload_window_idx
    ON metric.query_workload(database_id, query_id, user_id, is_toplevel, collected_at);
