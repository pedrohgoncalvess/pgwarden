-- depends: 20261031_02_index-advisor

ALTER TABLE metric_query_workload ADD COLUMN query TEXT;
ALTER TABLE metric_query_workload ADD COLUMN query_hash TEXT;
ALTER TABLE metric_query_workload ADD COLUMN user_name TEXT;
ALTER TABLE metric_query_workload ADD COLUMN statement_data TEXT;
CREATE INDEX query_workload_identity_idx ON metric_query_workload(database_id, query_id, collected_at DESC);
CREATE INDEX query_workload_hash_idx ON metric_query_workload(database_id, query_hash, collected_at DESC);

INSERT INTO collector_config_database (database_id, name, interval)
SELECT d.id, 'query_workload_collector', 60 FROM metadata_database d
WHERE NOT EXISTS (SELECT 1 FROM collector_config_database c
    WHERE c.database_id = d.id AND c.name = 'query_workload_collector');

CREATE TRIGGER default_query_workload AFTER INSERT ON metadata_database
BEGIN
    INSERT INTO collector_config_database (database_id, name, interval)
    VALUES (NEW.id, 'query_workload_collector', 60);
END;

