DELETE FROM "collector"."config_database"
WHERE name = 'native_query_collector';

CREATE OR REPLACE FUNCTION "collector"."fn_default_config_database"()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
    BEGIN
        INSERT INTO "collector"."config_database" (database_id, name, interval) VALUES
            (NEW.id, 'table_collector', 1800),
            (NEW.id, 'column_collector', 1800),
            (NEW.id, 'index_collector', 1800),
            (NEW.id, 'table_metric_collector', 1800),
            (NEW.id, 'column_metric_collector', 1800),
            (NEW.id, 'index_metric_collector', 1800),
            (NEW.id, 'lock_metric_collector', 3),
            (NEW.id, 'session_metric_collector', 3),
            (NEW.id, 'database_stat_collector', 3);
        RETURN NEW;
    END;
$$;

DROP TABLE IF EXISTS "metric"."native_query";

ALTER TABLE "collector"."config_database"
    ALTER COLUMN interval TYPE INTEGER
    USING CEIL(interval)::INTEGER;
