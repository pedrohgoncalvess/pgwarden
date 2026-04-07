-- depends:

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA "collector";
CREATE SCHEMA "metadata";
CREATE SCHEMA "metric";

CREATE TABLE "collector"."server" (
    id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    public_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    host TEXT NOT NULL,
    port TEXT NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    ssl_mode TEXT NOT NULL DEFAULT 'prefer',
    last_seen_at TIMESTAMPTZ,
    last_error TEXT,
    ignore_pattern TEXT,
    ignore_tables TEXT[],
    include_tables TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT server_pk PRIMARY KEY (id),
    CONSTRAINT server_public_id_uq UNIQUE (public_id),
    CONSTRAINT server_conn_uq UNIQUE (host, username),
    CONSTRAINT server_ssl_ck CHECK (ssl_mode IN ('disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full'))
);

COMMENT ON TABLE "collector"."server" IS 'PostgreSQL server registry. Holds encrypted connection credentials.';
COMMENT ON COLUMN "collector"."server".host IS '[encrypted] Server hostname or IP address.';
COMMENT ON COLUMN "collector"."server".port IS 'Server port. Not encrypted — not sensitive.';
COMMENT ON COLUMN "collector"."server".username IS '[encrypted] Username used to connect to this server.';
COMMENT ON COLUMN "collector"."server".password IS '[encrypted] Password. Never stored in plain text.';
COMMENT ON COLUMN "collector"."server".ssl_mode IS 'PostgreSQL SSL mode. Negotiated at server level, not per database.';
COMMENT ON COLUMN "collector"."server".last_seen_at IS 'Timestamp of the last successful connection attempt by the collector.';
COMMENT ON COLUMN "collector"."server".last_error IS 'Last connection error reported by the collector. Null when healthy.';

CREATE TABLE "metadata"."database" (
    id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    oid OID,
    public_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    server_id BIGINT NOT NULL,
    db_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_seen_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT database_pk PRIMARY KEY (id),
    CONSTRAINT database_public_id_uq UNIQUE (public_id),
    CONSTRAINT database_server_db_uq UNIQUE (server_id, db_name),
    CONSTRAINT database_server_fk FOREIGN KEY (server_id) REFERENCES "collector"."server" (id) ON DELETE CASCADE
);

COMMENT ON TABLE "metadata"."database" IS 'Individual databases within a monitored server. Each gets independent collection jobs.';
COMMENT ON COLUMN "metadata"."database".db_name IS '[encrypted] Database name.';
COMMENT ON COLUMN "metadata"."database".oid IS 'OID from pg_database. Populated after first successful connection.';
COMMENT ON COLUMN "metadata"."database".is_active IS 'When false, the collector skips this database without deleting the record.';
COMMENT ON COLUMN "metadata"."database".last_seen_at IS 'Timestamp of the last successful connection attempt by the collector.';
COMMENT ON COLUMN "metadata"."database".last_error IS 'Last connection error reported by the collector. Null when healthy.';

CREATE TABLE "metadata"."table" (
    id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    oid OID NOT NULL,
    public_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    database_id BIGINT NOT NULL,
    schema_name TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by BIGINT,
    updated_at TIMESTAMPTZ,
    deleted_by BIGINT,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT table_pk PRIMARY KEY (id),
    CONSTRAINT table_public_id_uq UNIQUE (public_id),
    CONSTRAINT table_oid_uq UNIQUE (database_id, oid),
    CONSTRAINT table_database_fk FOREIGN KEY (database_id) REFERENCES "metadata"."database" (id) ON DELETE CASCADE
);

COMMENT ON TABLE "metadata"."table" IS 'Catalog of managed tables with full audit trail (created/updated/deleted).';
COMMENT ON COLUMN "metadata"."table".id IS 'Internal surrogate key. Never exposed outside the database.';
COMMENT ON COLUMN "metadata"."table".public_id IS 'UUID exposed via API. Decouples internal PKs from external references.';
COMMENT ON COLUMN "metadata"."table".oid IS 'OID from pg_class. Unique per database, not globally.';
COMMENT ON COLUMN "metadata"."table".deleted_at IS 'Soft-delete marker. When set, the table is treated as removed.';
COMMENT ON COLUMN "metadata"."table".created_by IS 'ID of the user who created this record. References auth.users once available.';

CREATE TABLE "metadata"."column" (
    id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    public_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    table_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    data_type TEXT NOT NULL,
    is_nullable BOOLEAN NOT NULL DEFAULT TRUE,
    default_value TEXT,
    is_unique BOOLEAN NOT NULL DEFAULT FALSE,
    ordinal_position INTEGER NOT NULL,
    fk_table_id BIGINT,
    fk_column_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by BIGINT,
    updated_at TIMESTAMPTZ,
    updated_by BIGINT,
    deleted_at TIMESTAMPTZ,
    deleted_by BIGINT,
    CONSTRAINT column_pk_ PRIMARY KEY (id),
    CONSTRAINT column_public_id_uq UNIQUE (public_id),
    CONSTRAINT column_name_table_id_uq UNIQUE (table_id, name),
    CONSTRAINT column_table_fk FOREIGN KEY (table_id) REFERENCES "metadata"."table" (id) ON DELETE CASCADE,
    CONSTRAINT column_table_fk_fk FOREIGN KEY (fk_table_id) REFERENCES "metadata"."table" (id) ON DELETE SET NULL,
    CONSTRAINT column_column_fk FOREIGN KEY (fk_column_id) REFERENCES "metadata"."column" (id) ON DELETE SET NULL
);

CREATE INDEX ix_column_table_id ON "metadata"."column" (table_id);
CREATE INDEX ix_column_fk_table_id ON "metadata"."column" (fk_table_id) WHERE fk_table_id IS NOT NULL;

COMMENT ON TABLE "metadata"."column" IS 'Column metadata: type, nullability, default, uniqueness and optional FK relationship.';
COMMENT ON COLUMN "metadata"."column".id IS 'Internal surrogate key. Never exposed outside the database.';
COMMENT ON COLUMN "metadata"."column".public_id IS 'UUID exposed via API. Decouples internal PKs from external references.';
COMMENT ON COLUMN "metadata"."column".data_type IS 'PostgreSQL data type as reported by information_schema (e.g. text, integer, uuid).';
COMMENT ON COLUMN "metadata"."column".ordinal_position IS 'Column position as defined in pg_attribute / information_schema.columns.';
COMMENT ON COLUMN "metadata"."column".fk_table_id IS 'When this column is a FK: points to metadata.table.id of the referenced table.';
COMMENT ON COLUMN "metadata"."column".fk_column_id IS 'When this column is a FK: points to metadata.column.id of the referenced column.';
COMMENT ON COLUMN "metadata"."column".deleted_at IS 'Soft-delete marker. When set, the column is treated as removed.';

CREATE TABLE "metadata"."index" (
    id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    public_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    database_id BIGINT NOT NULL,
    table_id BIGINT NOT NULL,
    oid OID NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    definition TEXT NOT NULL,
    is_unique BOOLEAN NOT NULL DEFAULT FALSE,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by BIGINT,
    updated_at TIMESTAMPTZ,
    updated_by BIGINT,
    deleted_at TIMESTAMPTZ,
    deleted_by BIGINT,

    CONSTRAINT index_pk PRIMARY KEY (id),
    CONSTRAINT index_public_id_uq UNIQUE (public_id),
    CONSTRAINT index_database_oid_uq UNIQUE (database_id, oid),
    CONSTRAINT index_database_fk FOREIGN KEY (database_id) REFERENCES "metadata"."database" (id) ON DELETE CASCADE,
    CONSTRAINT index_table_fk FOREIGN KEY (table_id) REFERENCES "metadata"."table" (id) ON DELETE CASCADE
);

CREATE TABLE "metadata"."index_column" (
    index_id BIGINT NOT NULL,
    column_id BIGINT NOT NULL,
    ordinal_position INTEGER NOT NULL,

    CONSTRAINT index_column_pk PRIMARY KEY (index_id, column_id),
    CONSTRAINT idx_col_index_fk FOREIGN KEY (index_id) REFERENCES "metadata"."index" (id) ON DELETE CASCADE,
    CONSTRAINT idx_col_column_fk FOREIGN KEY (column_id) REFERENCES "metadata"."column" (id) ON DELETE CASCADE
);

CREATE TABLE "metadata"."table_history" (
    id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    table_id BIGINT NOT NULL,
    table_oid OID NOT NULL,
    schema_name TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by BIGINT,

    CONSTRAINT table_history_pk PRIMARY KEY (id),
    CONSTRAINT table_history_table_fk FOREIGN KEY (table_id) REFERENCES "metadata"."table"(id)
);

CREATE INDEX ix_table_history_table_id ON "metadata"."table_history" (table_id);

COMMENT ON TABLE "metadata"."table_history" IS 'Audit log of all changes to table. One row per change, capturing the state before the update.';
COMMENT ON COLUMN "metadata"."table_history".table_id IS 'References the original table.id that was modified.';
COMMENT ON COLUMN "metadata"."table_history".changed_at IS 'Timestamp when the change was detected by the collector.';
COMMENT ON COLUMN "metadata"."table_history".changed_by IS 'ID of the user or process that triggered the change. References auth.users once available.';

CREATE TABLE "metadata"."column_history" (
    id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    column_id BIGINT NOT NULL,
    table_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    data_type TEXT NOT NULL,
    is_nullable BOOLEAN NOT NULL,
    default_value TEXT,
    is_unique BOOLEAN NOT NULL,
    ordinal_position INTEGER NOT NULL,
    fk_table_id BIGINT,
    fk_column_id BIGINT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by BIGINT,

    CONSTRAINT column_history_pk PRIMARY KEY (id),
    CONSTRAINT column_history_column_fk FOREIGN KEY (column_id) REFERENCES "metadata"."column"(id)
);

CREATE INDEX ix_column_history_id ON "metadata"."column_history" (column_id);
CREATE INDEX ix_column_history_table_id ON "metadata"."column_history" (table_id);

COMMENT ON TABLE "metadata"."column_history" IS 'Audit log of all changes to column. One row per change, capturing the state before the update.';
COMMENT ON COLUMN "metadata"."column_history".column_id IS 'References the original column.id that was modified.';
COMMENT ON COLUMN "metadata"."column_history".changed_at IS 'Timestamp when the change was detected by the collector.';

CREATE OR REPLACE FUNCTION "metadata"."fn_table_history"()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
    BEGIN
        INSERT INTO "metadata"."table_history" (
            table_id, table_oid, schema_name, name, description, changed_at, changed_by
        ) VALUES (
            OLD.id, OLD.oid, OLD.schema_name, OLD.name, OLD.description, now(), OLD.updated_by
        );
        RETURN NEW;
    END;
$$;

CREATE TRIGGER trg_table_history
    BEFORE UPDATE ON "metadata"."table"
        FOR EACH ROW
            WHEN (
                OLD.oid IS DISTINCT FROM NEW.oid OR
                OLD.schema_name IS DISTINCT FROM NEW.schema_name OR
                OLD.name IS DISTINCT FROM NEW.name OR
                OLD.description IS DISTINCT FROM NEW.description
            )
EXECUTE FUNCTION "metadata"."fn_table_history"();

CREATE OR REPLACE FUNCTION "metadata"."fn_column_history"()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
    BEGIN
        INSERT INTO "metadata"."column_history" (
            column_id, table_id, name, description, data_type, is_nullable,
            default_value, is_unique, ordinal_position, fk_table_id, fk_column_id, changed_at, changed_by
        ) VALUES (
            OLD.id, OLD.table_id, OLD.name, OLD.description, OLD.data_type, OLD.is_nullable,
            OLD.default_value, OLD.is_unique, OLD.ordinal_position, OLD.fk_table_id, OLD.fk_column_id,
            now(), OLD.updated_by
        );
        RETURN NEW;
    END;
$$;

CREATE TRIGGER trg_column_history
    BEFORE UPDATE ON "metadata"."column"
        FOR EACH ROW
            WHEN (
                OLD.name IS DISTINCT FROM NEW.name OR
                OLD.description IS DISTINCT FROM NEW.description OR
                OLD.data_type IS DISTINCT FROM NEW.data_type OR
                OLD.is_nullable IS DISTINCT FROM NEW.is_nullable OR
                OLD.default_value IS DISTINCT FROM NEW.default_value OR
                OLD.is_unique IS DISTINCT FROM NEW.is_unique OR
                OLD.ordinal_position IS DISTINCT FROM NEW.ordinal_position OR
                OLD.fk_table_id IS DISTINCT FROM NEW.fk_table_id OR
                OLD.fk_column_id IS DISTINCT FROM NEW.fk_column_id
            )
EXECUTE FUNCTION "metadata"."fn_column_history"();

CREATE TABLE "collector"."config" (
    id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    name TEXT NOT NULL,
    interval INTEGER NOT NULL,
    is_paused BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'idle',
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_run_at TIMESTAMPTZ,
    last_error TEXT,
    run_count BIGINT NOT NULL DEFAULT 0,
    error_count BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ,

    CONSTRAINT pk_config PRIMARY KEY (id),
    CONSTRAINT uq_config_name UNIQUE (name)
);

INSERT INTO collector.config (name, interval) VALUES
('table_collector', 1800),
('column_collector', 1800),
('index_collector', 1800),
('table_metric_collector', 1800),
('column_metric_collector', 1800),
('index_metric_collector', 1800),
('lock_metric_collector', 3),
('session_metric_collector', 3);

COMMENT ON TABLE "collector"."config" IS 'Live configuration and status for each registered collector.';
COMMENT ON COLUMN "collector"."config".interval IS 'Interval in seconds between runs.';
COMMENT ON COLUMN "collector"."config".is_paused IS 'When true, the collector loop will block until resumed.';
COMMENT ON COLUMN "collector"."config".status IS 'Current status: idle, running, paused, error.';
COMMENT ON COLUMN "collector"."config".next_run_at IS 'Exact timestamp for the next scheduled run. Updated dynamically after success or force_run.';

CREATE TABLE "collector"."command" (
    id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    collector TEXT NOT NULL,
    command TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    executed_at TIMESTAMPTZ,
    error TEXT,
    CONSTRAINT pk_command PRIMARY KEY (id)
);

CREATE INDEX ix_command_pending ON "collector"."command" (created_at) WHERE executed_at IS NULL;

COMMENT ON TABLE "collector"."command" IS 'Command queue between API and collector process. API writes, collector consumes.';
COMMENT ON COLUMN "collector"."command".command IS 'pause | resume | force_run | set_interval';
COMMENT ON COLUMN "collector"."command".payload IS 'Optional JSON payload. Used by set_interval: {"interval": 60}';

CREATE TABLE "metric"."table" (
    collected_at TIMESTAMPTZ NOT NULL,
    table_id BIGINT NOT NULL,
    n_live_tup BIGINT,
    n_dead_tup BIGINT,
    table_size_bytes BIGINT,
    last_vacuum TIMESTAMPTZ,
    last_autovacuum TIMESTAMPTZ,
    last_analyze TIMESTAMPTZ,
    last_autoanalyze TIMESTAMPTZ,
    seq_scan BIGINT,
    idx_scan BIGINT,
    heap_blks_read BIGINT,
    heap_blks_hit BIGINT,

    CONSTRAINT table_metric_pk PRIMARY KEY (collected_at, table_id),
    CONSTRAINT table_metric_table_fk FOREIGN KEY (table_id) REFERENCES "metadata"."table"(id) ON DELETE CASCADE
);

SELECT create_hypertable('metric.table', 'collected_at');

CREATE TABLE "metric"."index" (
    collected_at TIMESTAMPTZ NOT NULL,
    index_id BIGINT NOT NULL,
    size BIGINT NOT NULL,
    scan_qt BIGINT,
    tup_read_qt BIGINT,
    tup_fetch_qt BIGINT,
    blks_read BIGINT,
    blks_hit BIGINT,

    CONSTRAINT index_metric_pk PRIMARY KEY (collected_at, index_id),
    CONSTRAINT index_metric_index_fk FOREIGN KEY (index_id) REFERENCES "metadata"."index"(id) ON DELETE CASCADE
);

SELECT create_hypertable('metric.index', 'collected_at');

CREATE TABLE "metric"."column" (
    collected_at TIMESTAMPTZ NOT NULL,
    column_id INTEGER NOT NULL,
    avg_width INTEGER,
    null_fraction REAL,
    n_distinct REAL,
    estimated_size BIGINT,

    CONSTRAINT column_size_pk PRIMARY KEY (collected_at, column_id),
    CONSTRAINT column_size_column_fk FOREIGN KEY (column_id) REFERENCES "metadata"."column"(id) ON DELETE CASCADE
);

SELECT create_hypertable('metric.column', 'collected_at');


CREATE TABLE "metric"."session" (
    collected_at TIMESTAMPTZ NOT NULL,
    database_id BIGINT NOT NULL,
    pid INTEGER NOT NULL,
    backend_start TIMESTAMPTZ NOT NULL,
    user_name TEXT,
    application_name TEXT,
    client_addr INET,
    state TEXT,
    wait_event_type TEXT,
    wait_event TEXT,
    query_start TIMESTAMPTZ,
    state_change TIMESTAMPTZ,
    query_preview TEXT,

    CONSTRAINT session_metric_pk PRIMARY KEY (collected_at, database_id, pid, backend_start),
    CONSTRAINT session_metric_database FOREIGN KEY (database_id) REFERENCES "metadata"."database"(id) ON DELETE CASCADE
);
SELECT create_hypertable('metric.session', 'collected_at');

CREATE TABLE "metric"."lock" (
    collected_at TIMESTAMPTZ NOT NULL,
    database_id BIGINT NOT NULL,
    table_id BIGINT NOT NULL,
    holder_pid INTEGER NOT NULL,
    type TEXT,
    mode TEXT,
    is_granted BOOLEAN,
    query_preview TEXT,

    CONSTRAINT lock_metric_pk PRIMARY KEY (collected_at, database_id, holder_pid, type, mode, table_id),
    CONSTRAINT lock_metric_database_fk FOREIGN KEY (database_id) REFERENCES "metadata"."database"(id) ON DELETE CASCADE,
    CONSTRAINT lock_metric_table_fk FOREIGN KEY (table_id) REFERENCES "metadata"."table"(id) ON DELETE CASCADE -- FK NOVA
);
SELECT create_hypertable('metric.lock', 'collected_at');