-- depends: 20261030_01_sqlite-collector

CREATE TABLE "metadata_table_history" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id INTEGER NOT NULL,
    table_oid INTEGER NOT NULL,
    schema_name TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    changed_by INTEGER,
    CONSTRAINT table_history_table_fk FOREIGN KEY (table_id) REFERENCES "metadata_table"(id)
);

CREATE TABLE "metadata_column_history" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    column_id INTEGER NOT NULL,
    table_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    data_type TEXT NOT NULL,
    is_nullable INTEGER NOT NULL,
    default_value TEXT,
    is_unique INTEGER NOT NULL,
    ordinal_position INTEGER NOT NULL,
    fk_table_id INTEGER,
    fk_column_id INTEGER,
    changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    changed_by INTEGER,
    CONSTRAINT column_history_column_fk FOREIGN KEY (column_id) REFERENCES "metadata_column"(id)
);

CREATE TABLE "collector_config_database" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    database_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    interval REAL NOT NULL,
    is_paused INTEGER NOT NULL DEFAULT FALSE,
    next_run_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    CONSTRAINT config_database_fk FOREIGN KEY (database_id) REFERENCES "metadata_database" (id) ON DELETE CASCADE
);

CREATE TABLE "collector_config_server" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    interval REAL NOT NULL,
    is_paused INTEGER NOT NULL DEFAULT FALSE,
    next_run_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    CONSTRAINT config_server_fk FOREIGN KEY (server_id) REFERENCES "collector_server" (id) ON DELETE CASCADE
);

CREATE TABLE "collector_command" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collector TEXT NOT NULL,
    command TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    executed_at TEXT,
    error TEXT
);

CREATE TABLE "collector_run" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_database_id INTEGER,
    config_server_id INTEGER,
    command_id INTEGER,
    status TEXT NOT NULL,
    errors TEXT,
    inserted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    finished_at TEXT,
    CONSTRAINT run_config_database_fk FOREIGN KEY (config_database_id) REFERENCES "collector_config_database" (id) ON DELETE CASCADE,
    CONSTRAINT run_config_server_fk FOREIGN KEY (config_server_id) REFERENCES "collector_config_server" (id) ON DELETE CASCADE,
    CONSTRAINT run_command_fk FOREIGN KEY (command_id) REFERENCES "collector_command" (id) ON DELETE SET NULL
);

CREATE TABLE "metric_table" (
    collected_at TEXT NOT NULL,
    table_id INTEGER NOT NULL,
    n_live_tup INTEGER,
    n_dead_tup INTEGER,
    table_size_bytes INTEGER,
    last_vacuum TEXT,
    last_autovacuum TEXT,
    last_analyze TEXT,
    last_autoanalyze TEXT,
    seq_scan INTEGER,
    idx_scan INTEGER,
    heap_blks_read INTEGER,
    heap_blks_hit INTEGER,

    modifications_since_last_analyze INTEGER,
    CONSTRAINT table_metric_pk PRIMARY KEY (collected_at, table_id),
    CONSTRAINT table_metric_table_fk FOREIGN KEY (table_id) REFERENCES "metadata_table"(id) ON DELETE CASCADE
);
