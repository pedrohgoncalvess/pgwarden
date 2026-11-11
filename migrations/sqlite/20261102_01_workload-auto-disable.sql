-- depends: 20261101_01_query-sources

ALTER TABLE collector_config_database ADD COLUMN consecutive_errors INTEGER NOT NULL DEFAULT 0;
ALTER TABLE collector_config_database ADD COLUMN warning TEXT;
UPDATE collector_config_database SET is_paused = TRUE WHERE name = 'query_workload_collector';

DROP TRIGGER default_query_workload;
CREATE TRIGGER default_query_workload AFTER INSERT ON metadata_database
BEGIN
    INSERT INTO collector_config_database (database_id, name, interval, is_paused)
    VALUES (NEW.id, 'query_workload_collector', 60, TRUE);
END;
