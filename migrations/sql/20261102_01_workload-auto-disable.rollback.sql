CREATE OR REPLACE FUNCTION collector.fn_default_query_workload() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO collector.config_database (database_id, name, interval)
    VALUES (NEW.id, 'query_workload_collector', 60);
    RETURN NEW;
END;
$$;
ALTER TABLE collector.config_database DROP COLUMN warning;
ALTER TABLE collector.config_database DROP COLUMN consecutive_errors;
