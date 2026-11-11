-- depends: 20261030_01_ingestion-projects 20261101_01_query-sources

CREATE SCHEMA retention;
CREATE TABLE retention.policy (
    scope TEXT NOT NULL CHECK (scope IN ('global', 'project', 'server')),
    scope_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    table_name TEXT NOT NULL DEFAULT '*',
    value INTEGER NOT NULL CHECK (value BETWEEN 1 AND 100000),
    unit TEXT NOT NULL CHECK (unit IN ('minutes','hours','days','weeks','months')),
    duration INTERVAL NOT NULL CHECK (duration > INTERVAL '0'),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, scope_id, table_name),
    CHECK ((scope = 'global') = (scope_id = '00000000-0000-0000-0000-000000000000'))
);
CREATE TABLE retention.run (
    table_name TEXT NOT NULL,
    server_id BIGINT NOT NULL REFERENCES collector.server(id) ON DELETE CASCADE,
    last_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_rows BIGINT NOT NULL,
    PRIMARY KEY (table_name, server_id)
);
CREATE TABLE retention.native_backup (
    table_name TEXT PRIMARY KEY,
    duration INTERVAL NOT NULL,
    scheduled BOOLEAN NOT NULL
);

DO $$
DECLARE job RECORD; period INTERVAL; months INTEGER; seconds NUMERIC;
        amount INTEGER; period_unit TEXT;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        FOR job IN SELECT * FROM timescaledb_information.jobs
            WHERE hypertable_schema = 'metric' AND proc_name = 'policy_retention'
        LOOP
            IF job.hypertable_name NOT IN ('column','cpu','database_stat','disk','index','io',
                'lock','native_query','query_workload','ram','session','table') THEN
                RAISE EXCEPTION 'Unsupported metric retention table: %', job.hypertable_name;
            END IF;
            IF job.config->>'drop_after' IS NULL THEN
                RAISE EXCEPTION 'Retention job % uses unsupported drop_created_before; convert it to drop_after before migration', job.job_id;
            END IF;
            period := (job.config->>'drop_after')::interval;
            months := EXTRACT(YEAR FROM period)::int * 12 + EXTRACT(MONTH FROM period)::int;
            seconds := EXTRACT(EPOCH FROM period);
            IF months > 0 AND period = make_interval(months => months) THEN
                amount := months; period_unit := 'months';
            ELSIF months = 0 AND mod(seconds,86400) = 0 THEN
                amount := seconds / 86400; period_unit := 'days';
            ELSIF months = 0 AND mod(seconds,3600) = 0 THEN
                amount := seconds / 3600; period_unit := 'hours';
            ELSIF months = 0 AND mod(seconds,60) = 0 THEN
                amount := seconds / 60; period_unit := 'minutes';
            ELSE
                RAISE EXCEPTION 'Retention job % has a mixed or sub-minute interval; convert it before migration', job.job_id;
            END IF;
            INSERT INTO retention.native_backup VALUES
                (job.hypertable_name, (job.config->>'drop_after')::interval, job.scheduled);
            INSERT INTO retention.policy(scope, table_name, value, unit, duration, enabled)
            VALUES ('global', job.hypertable_name, amount, period_unit, period, job.scheduled);
            -- Shared chunks must never expire ahead of an individual scope's policy.
            PERFORM remove_retention_policy(format('metric.%I', job.hypertable_name)::regclass);
        END LOOP;
    END IF;
END;
$$;
