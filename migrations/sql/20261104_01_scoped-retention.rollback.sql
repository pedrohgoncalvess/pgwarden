DO $$
DECLARE item RECORD; new_job INTEGER;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        FOR item IN SELECT * FROM retention.native_backup LOOP
            SELECT add_retention_policy(format('metric.%I', item.table_name)::regclass,
                drop_after => item.duration, if_not_exists => TRUE) INTO new_job;
            IF new_job IS NOT NULL THEN
                PERFORM alter_job(new_job, scheduled => item.scheduled);
            END IF;
        END LOOP;
    END IF;
END;
$$;
DROP SCHEMA retention CASCADE;
