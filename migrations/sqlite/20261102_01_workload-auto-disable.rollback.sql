DROP TRIGGER default_query_workload;
CREATE TRIGGER default_query_workload AFTER INSERT ON metadata_database
BEGIN
    INSERT INTO collector_config_database (database_id, name, interval)
    VALUES (NEW.id, 'query_workload_collector', 60);
END;
ALTER TABLE collector_config_database DROP COLUMN warning;
ALTER TABLE collector_config_database DROP COLUMN consecutive_errors;
