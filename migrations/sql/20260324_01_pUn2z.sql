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
    ignore_patterns TEXT[],
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
COMMENT ON COLUMN "metadata"."database".db_name IS 'Database name.';
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

COMMENT ON TABLE "metadata"."index" IS 'Catalog of indexes for each managed table.';
COMMENT ON COLUMN "metadata"."index".oid IS 'OID from pg_index. Unique per database.';
COMMENT ON COLUMN "metadata"."index".type IS 'Index access method (e.g. btree, hash, gist).';
COMMENT ON COLUMN "metadata"."index".definition IS 'Full SQL definition of the index.';
COMMENT ON COLUMN "metadata"."index".is_primary IS 'True if this is the primary key of the table.';

CREATE TABLE "metadata"."index_column" (
    index_id BIGINT NOT NULL,
    column_id BIGINT NOT NULL,
    ordinal_position INTEGER NOT NULL,

    CONSTRAINT index_column_pk PRIMARY KEY (index_id, column_id),
    CONSTRAINT idx_col_index_fk FOREIGN KEY (index_id) REFERENCES "metadata"."index" (id) ON DELETE CASCADE,
    CONSTRAINT idx_col_column_fk FOREIGN KEY (column_id) REFERENCES "metadata"."column" (id) ON DELETE CASCADE
);

COMMENT ON TABLE "metadata"."index_column" IS 'Relationship between indexes and their constituent columns, including ordinal position.';

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

CREATE TABLE "collector"."config_database" (
    id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    database_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    interval INTEGER NOT NULL,
    is_paused BOOLEAN NOT NULL DEFAULT FALSE,
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT config_database_pk PRIMARY KEY (id),
    CONSTRAINT config_database_fk FOREIGN KEY (database_id) REFERENCES "metadata"."database" (id) ON DELETE CASCADE
);

CREATE TABLE "collector"."config_server" (
    id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    server_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    interval INTEGER NOT NULL,
    is_paused BOOLEAN NOT NULL DEFAULT FALSE,
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT config_server_pk PRIMARY KEY (id),
    CONSTRAINT config_server_fk FOREIGN KEY (server_id) REFERENCES "collector"."server" (id) ON DELETE CASCADE
);

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

CREATE TABLE "collector"."run" (
    id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    config_database_id INTEGER,
    config_server_id INTEGER,
    command_id BIGINT,
    status TEXT NOT NULL,
    errors TEXT[],
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,

    CONSTRAINT run_pk PRIMARY KEY (id),
    CONSTRAINT run_config_database_fk FOREIGN KEY (config_database_id) REFERENCES "collector"."config_database" (id) ON DELETE CASCADE,
    CONSTRAINT run_config_server_fk FOREIGN KEY (config_server_id) REFERENCES "collector"."config_server" (id) ON DELETE CASCADE,
    CONSTRAINT run_command_fk FOREIGN KEY (command_id) REFERENCES "collector"."command" (id) ON DELETE SET NULL
);

COMMENT ON TABLE "collector"."run" IS 'Execution log for collector jobs. Tracks success, failure, and any errors encountered during a specific run.';
COMMENT ON COLUMN "collector"."run".status IS 'Current status of the run (e.g. success, error).';
COMMENT ON COLUMN "collector"."run".errors IS 'Array of error messages if the run failed.';
COMMENT ON COLUMN "collector"."run".command_id IS 'References the command that triggered this run (e.g. force_run). Null for scheduled runs.';

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
            (NEW.id, 'session_metric_collector', 3);
        RETURN NEW;
    END;
$$;

CREATE TRIGGER trg_default_config_database
    AFTER INSERT ON "metadata"."database"
        FOR EACH ROW
EXECUTE FUNCTION "collector"."fn_default_config_database"();

CREATE OR REPLACE FUNCTION "collector"."fn_default_config_server"()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
    BEGIN
        INSERT INTO "collector"."config_server" (server_id, name, interval) VALUES
            (NEW.id, 'cpu_collector', 20),
            (NEW.id, 'ram_collector', 20),
            (NEW.id, 'io_collector', 5),
            (NEW.id, 'disk_collector', 1800);
        RETURN NEW;
    END;
$$;

CREATE TRIGGER trg_default_config_server
    AFTER INSERT ON "collector"."server"
        FOR EACH ROW
EXECUTE FUNCTION "collector"."fn_default_config_server"();

COMMENT ON TABLE "collector"."config_database" IS 'Per-database collector configuration. Auto-populated via trigger when a database is registered.';
COMMENT ON COLUMN "collector"."config_database".interval IS 'Interval in seconds between runs.';
COMMENT ON COLUMN "collector"."config_database".is_paused IS 'When true, the collector loop skips this job.';
COMMENT ON COLUMN "collector"."config_database".next_run_at IS 'Next scheduled run. Updated dynamically after each execution.';

COMMENT ON TABLE "collector"."config_server" IS 'Per-server collector configuration. Auto-populated via trigger when a server is registered.';
COMMENT ON COLUMN "collector"."config_server".interval IS 'Interval in seconds between runs.';
COMMENT ON COLUMN "collector"."config_server".is_paused IS 'When true, the collector loop skips this job.';
COMMENT ON COLUMN "collector"."config_server".next_run_at IS 'Next scheduled run. Updated dynamically after each execution.';



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

COMMENT ON TABLE "metric"."table" IS 'Timeseries data for table-level statistics (sequential scans, index scans, tuples, etc.).';
COMMENT ON COLUMN "metric"."table".collected_at IS 'Timestamp of the metrics collection.';
COMMENT ON COLUMN "metric"."table".n_live_tup IS 'Estimated number of live rows.';
COMMENT ON COLUMN "metric"."table".n_dead_tup IS 'Estimated number of dead rows.';
COMMENT ON COLUMN "metric"."table".table_size_bytes IS 'Total disk space used by the table including all forks (FSM, VM) and toast.';

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

COMMENT ON TABLE "metric"."index" IS 'Timeseries data for index-level statistics (scans, rows read/fetched, I/O blocks).';
COMMENT ON COLUMN "metric"."index".collected_at IS 'Timestamp of the metrics collection.';
COMMENT ON COLUMN "metric"."index".size IS 'Total disk space used by the index.';

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

COMMENT ON TABLE "metric"."column" IS 'Timeseries data for column-level statistics (average width, null fraction, etc.).';
COMMENT ON COLUMN "metric"."column".collected_at IS 'Timestamp of the metrics collection.';
COMMENT ON COLUMN "metric"."column".avg_width IS 'Average width in bytes of column entries.';
COMMENT ON COLUMN "metric"."column".null_fraction IS 'Fraction of column entries that are null.';

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

COMMENT ON TABLE "metric"."session" IS 'Timeseries data for active database sessions, capturing state, wait events, and query progress.';
COMMENT ON COLUMN "metric"."session".collected_at IS 'Timestamp of the metrics collection.';
COMMENT ON COLUMN "metric"."session".pid IS 'Process ID of the backend.';
COMMENT ON COLUMN "metric"."session".state IS 'Current status of the backend (e.g. active, idle).';
COMMENT ON COLUMN "metric"."session".query_preview IS 'Snippet of the query being executed.';
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

COMMENT ON TABLE "metric"."lock" IS 'Timeseries data for database locks, identifying holders and waiters.';
COMMENT ON COLUMN "metric"."lock".collected_at IS 'Timestamp of the metrics collection.';
COMMENT ON COLUMN "metric"."lock".holder_pid IS 'Process ID of the session holding or requesting the lock.';
COMMENT ON COLUMN "metric"."lock".type IS 'Type of lockable object (e.g. relation, transactionid).';
COMMENT ON COLUMN "metric"."lock".mode IS 'Lock mode (e.g. AccessShareLock, ExclusiveLock).';
COMMENT ON COLUMN "metric"."lock".is_granted IS 'True if the lock is held, false if it is being waited for.';
SELECT create_hypertable('metric.lock', 'collected_at');

CREATE TABLE "metric"."cpu" (
    collected_at  TIMESTAMPTZ NOT NULL,
    server_id     BIGINT NOT NULL,
    cpu_percent   REAL,
    cpu_count     INTEGER,

    CONSTRAINT cpu_metric_pk PRIMARY KEY (collected_at, server_id),
    CONSTRAINT cpu_metric_server_fk FOREIGN KEY (server_id)
        REFERENCES "collector"."server" (id) ON DELETE CASCADE
);

SELECT create_hypertable('metric.cpu', 'collected_at');

COMMENT ON TABLE "metric"."cpu" IS 'Timeseries data for server CPU usage.';
COMMENT ON COLUMN "metric"."cpu".cpu_percent IS 'Total CPU usage percentage across all cores.';
COMMENT ON COLUMN "metric"."cpu".cpu_count IS 'Number of logical CPU cores.';

CREATE TABLE "metric"."ram" (
    collected_at    TIMESTAMPTZ NOT NULL,
    server_id       BIGINT NOT NULL,
    total_bytes     BIGINT,
    used_bytes      BIGINT,
    available_bytes BIGINT,
    percent         REAL,

    CONSTRAINT ram_metric_pk PRIMARY KEY (collected_at, server_id),
    CONSTRAINT ram_metric_server_fk FOREIGN KEY (server_id)
        REFERENCES "collector"."server" (id) ON DELETE CASCADE
);

SELECT create_hypertable('metric.ram', 'collected_at');

COMMENT ON TABLE "metric"."ram" IS 'Timeseries data for server RAM usage.';
COMMENT ON COLUMN "metric"."ram".total_bytes IS 'Total physical memory in bytes.';
COMMENT ON COLUMN "metric"."ram".used_bytes IS 'Used physical memory in bytes.';
COMMENT ON COLUMN "metric"."ram".available_bytes IS 'Available memory in bytes (includes buffers/cache).';
COMMENT ON COLUMN "metric"."ram".percent IS 'Memory usage percentage.';

CREATE TABLE "metric"."disk" (
    collected_at    TIMESTAMPTZ NOT NULL,
    server_id       BIGINT NOT NULL,
    mount_point     TEXT NOT NULL,
    total_bytes     BIGINT,
    used_bytes      BIGINT,
    free_bytes      BIGINT,
    percent         REAL,

    CONSTRAINT disk_metric_pk PRIMARY KEY (collected_at, server_id, mount_point),
    CONSTRAINT disk_metric_server_fk FOREIGN KEY (server_id)
        REFERENCES "collector"."server" (id) ON DELETE CASCADE
);

SELECT create_hypertable('metric.disk', 'collected_at');

COMMENT ON TABLE "metric"."disk" IS 'Timeseries data for server disk usage per mount point.';
COMMENT ON COLUMN "metric"."disk".mount_point IS 'Filesystem mount point (e.g. /, /data).';
COMMENT ON COLUMN "metric"."disk".percent IS 'Disk usage percentage for this mount point.';

CREATE TABLE "metric"."io" (
    collected_at    TIMESTAMPTZ NOT NULL,
    server_id       BIGINT NOT NULL,
    read_bytes      BIGINT,
    write_bytes     BIGINT,
    read_count      BIGINT,
    write_count     BIGINT,

    CONSTRAINT io_metric_pk PRIMARY KEY (collected_at, server_id),
    CONSTRAINT io_metric_server_fk FOREIGN KEY (server_id)
        REFERENCES "collector"."server" (id) ON DELETE CASCADE
);

SELECT create_hypertable('metric.io', 'collected_at');

COMMENT ON TABLE "metric"."io" IS 'Timeseries data for server disk I/O counters (cumulative since boot).';
COMMENT ON COLUMN "metric"."io".read_bytes IS 'Cumulative bytes read from disk since boot.';
COMMENT ON COLUMN "metric"."io".write_bytes IS 'Cumulative bytes written to disk since boot.';
COMMENT ON COLUMN "metric"."io".read_count IS 'Cumulative number of read operations since boot.';
COMMENT ON COLUMN "metric"."io".write_count IS 'Cumulative number of write operations since boot.';