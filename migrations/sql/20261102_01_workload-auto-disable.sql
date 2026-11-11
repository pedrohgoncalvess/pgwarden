-- depends: 20261101_01_query-sources

ALTER TABLE collector.config_database ADD COLUMN consecutive_errors INTEGER NOT NULL DEFAULT 0;
ALTER TABLE collector.config_database ADD COLUMN warning TEXT;
UPDATE collector.config_database SET is_paused = TRUE WHERE name = 'query_workload_collector';

CREATE OR REPLACE FUNCTION collector.fn_default_query_workload() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO collector.config_database (database_id, name, interval, is_paused)
    VALUES (NEW.id, 'query_workload_collector', 60, TRUE);
    RETURN NEW;
END;
$$;
