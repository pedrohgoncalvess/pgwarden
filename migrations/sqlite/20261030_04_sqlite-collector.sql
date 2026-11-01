-- depends: 20261030_03_sqlite-collector

CREATE TABLE "metric_ram" (
    collected_at    TEXT NOT NULL,
    server_id       INTEGER NOT NULL,
    total_bytes     INTEGER,
    used_bytes      INTEGER,
    available_bytes INTEGER,
    percent         REAL,

    CONSTRAINT ram_metric_pk PRIMARY KEY (collected_at, server_id),
    CONSTRAINT ram_metric_server_fk FOREIGN KEY (server_id)
        REFERENCES "collector_server" (id) ON DELETE CASCADE
);

CREATE TABLE "metric_disk" (
    collected_at    TEXT NOT NULL,
    server_id       INTEGER NOT NULL,
    mount_point     TEXT NOT NULL,
    total_bytes     INTEGER,
    used_bytes      INTEGER,
    free_bytes      INTEGER,
    percent         REAL,

    CONSTRAINT disk_metric_pk PRIMARY KEY (collected_at, server_id, mount_point),
    CONSTRAINT disk_metric_server_fk FOREIGN KEY (server_id)
        REFERENCES "collector_server" (id) ON DELETE CASCADE
);

CREATE TABLE "metric_io" (
    collected_at    TEXT NOT NULL,
    server_id       INTEGER NOT NULL,
    read_bytes      INTEGER,
    write_bytes     INTEGER,
    read_count      INTEGER,
    write_count     INTEGER,

    CONSTRAINT io_metric_pk PRIMARY KEY (collected_at, server_id),
    CONSTRAINT io_metric_server_fk FOREIGN KEY (server_id)
        REFERENCES "collector_server" (id) ON DELETE CASCADE
);

CREATE TABLE "metric_database_stat" (
    collected_at      TEXT NOT NULL,
    database_id       INTEGER NOT NULL REFERENCES "metadata_database"(id) ON DELETE CASCADE,
    xact_commit       INTEGER,
    xact_rollback     INTEGER,
    blks_read         INTEGER,
    blks_hit          INTEGER,
    tup_returned      INTEGER,
    tup_fetched       INTEGER,
    tup_inserted      INTEGER,
    tup_updated       INTEGER,
    tup_deleted       INTEGER,
    conflicts         INTEGER,
    deadlocks         INTEGER,
    db_size_bytes     INTEGER,
    CONSTRAINT database_stat_pk PRIMARY KEY (collected_at, database_id)
);

CREATE TABLE "metric_native_query" (
    collected_at TEXT NOT NULL,
    database_id INTEGER NOT NULL,
    pid INTEGER NOT NULL,
    leader_pid INTEGER,
    usesysid INTEGER,
    user_name TEXT,
    application_name TEXT,
    client_addr TEXT,
    client_hostname TEXT,
    client_port INTEGER,
    backend_start TEXT NOT NULL,
    xact_start TEXT,
    query_start TEXT,
    state_change TEXT,
    wait_event_type TEXT,
    wait_event TEXT,
    state TEXT,
    backend_xid TEXT,
    backend_xmin TEXT,
    query_id INTEGER,
    backend_type TEXT,
    query TEXT,
    query_hash TEXT,
    query_duration_ms REAL,
    transaction_duration_ms REAL,
    backend_duration_ms REAL,

    CONSTRAINT native_query_metric_pk PRIMARY KEY (collected_at, database_id, pid, backend_start),
    CONSTRAINT native_query_metric_database_fk FOREIGN KEY (database_id) REFERENCES "metadata_database"(id) ON DELETE CASCADE
);

CREATE TABLE "metadata_index_history" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    index_id     INTEGER NOT NULL,
    table_id     INTEGER NOT NULL,
    index_oid    INTEGER NOT NULL,
    name         TEXT NOT NULL,
    type         TEXT NOT NULL,
    definition   TEXT NOT NULL,
    is_unique    INTEGER NOT NULL,
    is_primary   INTEGER NOT NULL,
    changed_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    changed_by   INTEGER,
    CONSTRAINT index_history_index_fk FOREIGN KEY (index_id) REFERENCES "metadata_index"(id) ON DELETE CASCADE,
    CONSTRAINT index_history_table_fk FOREIGN KEY (table_id) REFERENCES "metadata_table"(id) ON DELETE CASCADE
);

CREATE TABLE "base_service_heartbeat" (
    service TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),

    CONSTRAINT "service_heartbeat_service_ck"
        CHECK (service IN ('collector', 'analytics', 'notifier'))
);
