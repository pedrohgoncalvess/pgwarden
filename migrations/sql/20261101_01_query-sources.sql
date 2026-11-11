-- depends: 20261031_02_index-advisor

ALTER TABLE metric.query_workload ADD COLUMN query TEXT;
ALTER TABLE metric.query_workload ADD COLUMN query_hash TEXT;
ALTER TABLE metric.query_workload ADD COLUMN user_name TEXT;
ALTER TABLE metric.query_workload ADD COLUMN statement_data TEXT;
CREATE INDEX query_workload_identity_idx ON metric.query_workload(database_id, query_id, collected_at DESC);
CREATE INDEX query_workload_hash_idx ON metric.query_workload(database_id, query_hash, collected_at DESC);

ALTER TABLE analytics.query ADD COLUMN pg_query_id BIGINT;
ALTER TABLE analytics.query ADD COLUMN seen_activity BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE analytics.query ADD COLUMN seen_statements BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE analytics.query DROP CONSTRAINT query_database_query_key;
ALTER TABLE analytics.query ADD CONSTRAINT query_database_query_identity_key UNIQUE (database_id, query, pg_query_id);
CREATE INDEX query_pg_identity_idx ON analytics.query(database_id, pg_query_id);

INSERT INTO collector.config_database (database_id, name, interval)
SELECT d.id, 'query_workload_collector', 60 FROM metadata.database d
WHERE NOT EXISTS (SELECT 1 FROM collector.config_database c
    WHERE c.database_id = d.id AND c.name = 'query_workload_collector');

CREATE FUNCTION collector.fn_default_query_workload() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO collector.config_database (database_id, name, interval)
    VALUES (NEW.id, 'query_workload_collector', 60);
    RETURN NEW;
END;
$$;
CREATE TRIGGER default_query_workload AFTER INSERT ON metadata.database
FOR EACH ROW EXECUTE FUNCTION collector.fn_default_query_workload();
