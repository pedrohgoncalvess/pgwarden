-- depends: 

CREATE TABLE "collector_server" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL,
    host TEXT NOT NULL,
    port TEXT NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    ssl_mode TEXT NOT NULL DEFAULT 'prefer',
    last_seen_at TEXT,
    last_error TEXT,
    ignore_patterns TEXT,
    ignore_tables TEXT,
    include_tables TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    updated_at TEXT,
    deleted_at TEXT,
    CONSTRAINT server_public_id_uq UNIQUE (public_id),
    CONSTRAINT server_name_uq UNIQUE (name),
    CONSTRAINT server_ssl_ck CHECK (ssl_mode IN ('disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full'))
);

CREATE TABLE "metadata_database" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oid INTEGER,
    public_id TEXT NOT NULL DEFAULT (lower(hex(randomblob(16)))),
    server_id INTEGER NOT NULL,
    db_name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT TRUE,
    last_seen_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    updated_at TEXT,
    deleted_at TEXT,
    CONSTRAINT database_public_id_uq UNIQUE (public_id),
    CONSTRAINT database_server_db_uq UNIQUE (server_id, db_name),
    CONSTRAINT database_server_fk FOREIGN KEY (server_id) REFERENCES "collector_server" (id) ON DELETE CASCADE
);

CREATE TABLE "metadata_table" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oid INTEGER NOT NULL,
    public_id TEXT NOT NULL DEFAULT (lower(hex(randomblob(16)))),
    database_id INTEGER NOT NULL,
    schema_name TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    updated_by INTEGER,
    updated_at TEXT,
    deleted_by INTEGER,
    deleted_at TEXT,
    CONSTRAINT table_public_id_uq UNIQUE (public_id),
    CONSTRAINT table_oid_uq UNIQUE (database_id, oid),
    CONSTRAINT table_database_fk FOREIGN KEY (database_id) REFERENCES "metadata_database" (id) ON DELETE CASCADE
);

CREATE TABLE "metadata_column" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL DEFAULT (lower(hex(randomblob(16)))),
    table_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    data_type TEXT NOT NULL,
    is_nullable INTEGER NOT NULL DEFAULT TRUE,
    default_value TEXT,
    is_unique INTEGER NOT NULL DEFAULT FALSE,
    ordinal_position INTEGER NOT NULL,
    fk_table_id INTEGER,
    fk_column_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    created_by INTEGER,
    updated_at TEXT,
    updated_by INTEGER,
    deleted_at TEXT,
    deleted_by INTEGER,
    CONSTRAINT column_public_id_uq UNIQUE (public_id),
    CONSTRAINT column_name_table_id_uq UNIQUE (table_id, name),
    CONSTRAINT column_table_fk FOREIGN KEY (table_id) REFERENCES "metadata_table" (id) ON DELETE CASCADE,
    CONSTRAINT column_table_fk_fk FOREIGN KEY (fk_table_id) REFERENCES "metadata_table" (id) ON DELETE SET NULL,
    CONSTRAINT column_column_fk FOREIGN KEY (fk_column_id) REFERENCES "metadata_column" (id) ON DELETE SET NULL
);

CREATE TABLE "metadata_index" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL DEFAULT (lower(hex(randomblob(16)))),
    database_id INTEGER NOT NULL,
    table_id INTEGER NOT NULL,
    oid INTEGER NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    definition TEXT NOT NULL,
    is_unique INTEGER NOT NULL DEFAULT FALSE,
    is_primary INTEGER NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    created_by INTEGER,
    updated_at TEXT,
    updated_by INTEGER,
    deleted_at TEXT,
    deleted_by INTEGER,
    CONSTRAINT index_public_id_uq UNIQUE (public_id),
    CONSTRAINT index_database_oid_uq UNIQUE (database_id, oid),
    CONSTRAINT index_database_fk FOREIGN KEY (database_id) REFERENCES "metadata_database" (id) ON DELETE CASCADE,
    CONSTRAINT index_table_fk FOREIGN KEY (table_id) REFERENCES "metadata_table" (id) ON DELETE CASCADE
);

CREATE TABLE "metadata_index_column" (
    index_id INTEGER NOT NULL,
    column_id INTEGER NOT NULL,
    ordinal_position INTEGER NOT NULL,

    CONSTRAINT index_column_pk PRIMARY KEY (index_id, column_id),
    CONSTRAINT idx_col_index_fk FOREIGN KEY (index_id) REFERENCES "metadata_index" (id) ON DELETE CASCADE,
    CONSTRAINT idx_col_column_fk FOREIGN KEY (column_id) REFERENCES "metadata_column" (id) ON DELETE CASCADE
);
