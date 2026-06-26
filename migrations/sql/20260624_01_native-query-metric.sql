ALTER TABLE "collector"."config_database"
    ALTER COLUMN interval TYPE DOUBLE PRECISION
    USING interval::DOUBLE PRECISION;

CREATE TABLE "metric"."native_query" (
    collected_at TIMESTAMPTZ NOT NULL,
    database_id BIGINT NOT NULL,
    pid INTEGER NOT NULL,
    leader_pid INTEGER,
    usesysid OID,
    user_name TEXT,
    application_name TEXT,
    client_addr INET,
    client_hostname TEXT,
    client_port INTEGER,
    backend_start TIMESTAMPTZ NOT NULL,
    xact_start TIMESTAMPTZ,
    query_start TIMESTAMPTZ,
    state_change TIMESTAMPTZ,
    wait_event_type TEXT,
    wait_event TEXT,
    state TEXT,
    backend_xid TEXT,
    backend_xmin TEXT,
    query_id BIGINT,
    backend_type TEXT,
    query TEXT,
    query_hash TEXT,
    query_duration_ms DOUBLE PRECISION,
    transaction_duration_ms DOUBLE PRECISION,
    backend_duration_ms DOUBLE PRECISION,

    CONSTRAINT native_query_metric_pk PRIMARY KEY (collected_at, database_id, pid, backend_start),
    CONSTRAINT native_query_metric_database_fk FOREIGN KEY (database_id) REFERENCES "metadata"."database"(id) ON DELETE CASCADE
);

COMMENT ON TABLE "metric"."native_query" IS 'Timeseries query monitoring collected from pg_stat_activity. Keeps native active query history.';
COMMENT ON COLUMN "metric"."native_query".query IS 'Full SQL text reported by pg_stat_activity at collection time.';
COMMENT ON COLUMN "metric"."native_query".query_hash IS 'MD5 hash of the query text to group repeated query samples.';
COMMENT ON COLUMN "metric"."native_query".query_duration_ms IS 'Milliseconds since query_start at collection time.';
COMMENT ON COLUMN "metric"."native_query".transaction_duration_ms IS 'Milliseconds since xact_start at collection time.';

SELECT create_hypertable('metric.native_query', 'collected_at');

CREATE INDEX native_query_database_collected_idx
    ON "metric"."native_query" (database_id, collected_at DESC);

CREATE INDEX native_query_database_state_idx
    ON "metric"."native_query" (database_id, state, collected_at DESC);

CREATE INDEX native_query_hash_collected_idx
    ON "metric"."native_query" (query_hash, collected_at DESC);

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
            (NEW.id, 'database_stat_collector', 3),
            (NEW.id, 'native_query_collector', 0.5);
        RETURN NEW;
    END;
$$;

INSERT INTO "collector"."config_database" (database_id, name, interval)
SELECT d.id, 'native_query_collector', 0.5
FROM "metadata"."database" d
WHERE NOT EXISTS (
    SELECT 1
    FROM "collector"."config_database" c
    WHERE c.database_id = d.id
      AND c.name = 'native_query_collector'
);
