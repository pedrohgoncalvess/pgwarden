-- depends: 20261030_02_sqlite-collector

CREATE TABLE "metric_index" (
    collected_at TEXT NOT NULL,
    index_id INTEGER NOT NULL,
    size INTEGER NOT NULL,
    scan_qt INTEGER,
    tup_read_qt INTEGER,
    tup_fetch_qt INTEGER,
    blks_read INTEGER,
    blks_hit INTEGER,

    CONSTRAINT index_metric_pk PRIMARY KEY (collected_at, index_id),
    CONSTRAINT index_metric_index_fk FOREIGN KEY (index_id) REFERENCES "metadata_index"(id) ON DELETE CASCADE
);

CREATE TABLE "metric_column" (
    collected_at TEXT NOT NULL,
    column_id INTEGER NOT NULL,
    avg_width INTEGER,
    null_fraction REAL,
    n_distinct REAL,
    estimated_size INTEGER,

    CONSTRAINT column_size_pk PRIMARY KEY (collected_at, column_id),
    CONSTRAINT column_size_column_fk FOREIGN KEY (column_id) REFERENCES "metadata_column"(id) ON DELETE CASCADE
);

CREATE TABLE "metric_session" (
    collected_at TEXT NOT NULL,
    database_id INTEGER NOT NULL,
    pid INTEGER NOT NULL,
    backend_start TEXT NOT NULL,
    user_name TEXT,
    application_name TEXT,
    client_addr TEXT,
    state TEXT,
    wait_event_type TEXT,
    wait_event TEXT,
    query_start TEXT,
    state_change TEXT,
    query_preview TEXT,

    CONSTRAINT session_metric_pk PRIMARY KEY (collected_at, database_id, pid, backend_start),
    CONSTRAINT session_metric_database FOREIGN KEY (database_id) REFERENCES "metadata_database"(id) ON DELETE CASCADE
);

CREATE TABLE "metric_lock" (
    collected_at TEXT NOT NULL,
    database_id INTEGER NOT NULL,
    table_id INTEGER NOT NULL,
    holder_pid INTEGER NOT NULL,
    type TEXT,
    mode TEXT,
    is_granted INTEGER,
    query_preview TEXT,

    CONSTRAINT lock_metric_pk PRIMARY KEY (collected_at, database_id, holder_pid, type, mode, table_id),
    CONSTRAINT lock_metric_database_fk FOREIGN KEY (database_id) REFERENCES "metadata_database"(id) ON DELETE CASCADE,
    CONSTRAINT lock_metric_table_fk FOREIGN KEY (table_id) REFERENCES "metadata_table"(id) ON DELETE CASCADE
);

CREATE TABLE "metric_cpu" (
    collected_at  TEXT NOT NULL,
    server_id     INTEGER NOT NULL,
    cpu_percent   REAL,
    cpu_count     INTEGER,

    CONSTRAINT cpu_metric_pk PRIMARY KEY (collected_at, server_id),
    CONSTRAINT cpu_metric_server_fk FOREIGN KEY (server_id)
        REFERENCES "collector_server" (id) ON DELETE CASCADE
);
