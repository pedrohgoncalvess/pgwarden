-- docs-tags-history
-- depends: 20260424_02_tsdbop-timescale-tuning

CREATE SCHEMA IF NOT EXISTS doc;

CREATE TABLE "doc"."tag" (
    id BIGSERIAL,
    public_id UUID NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    server_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    color TEXT DEFAULT '#07a96e',
    type VARCHAR(20) NOT NULL DEFAULT 'default',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_tag_server_fk FOREIGN KEY (server_id) REFERENCES collector.server(id) ON DELETE CASCADE,
    CONSTRAINT doc_tag_server_name_uq UNIQUE (server_id, name)
);

COMMENT ON TABLE "doc"."tag" IS 'Metadata tags for databases, schemas, tables, columns, indexes and queries. Color-coded and typed for categorization.';
COMMENT ON COLUMN "doc"."tag".server_id IS 'Server that owns this tag namespace.';
COMMENT ON COLUMN "doc"."tag".type IS 'Tag category type (e.g. default, status, team).';
COMMENT ON COLUMN "doc"."tag".color IS 'Hex color code for visual identification of the tag in the UI.';

CREATE TABLE "doc"."database" (
    id BIGSERIAL,
    database_id BIGINT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    updated_by BIGINT,

    CONSTRAINT doc_database_pk PRIMARY KEY (id),
    CONSTRAINT doc_database_database_fk FOREIGN KEY (database_id) REFERENCES metadata.database(id) ON DELETE CASCADE
);

COMMENT ON TABLE "doc"."database" IS 'Documentation record for a monitored database.';

CREATE TABLE "doc"."schema" (
    id BIGSERIAL,
    database_id BIGINT NOT NULL,
    schema_name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    updated_by BIGINT,

    CONSTRAINT doc_schema_pk PRIMARY KEY (id),
    CONSTRAINT doc_schema_database_fk FOREIGN KEY (database_id) REFERENCES metadata.database(id) ON DELETE CASCADE,
    CONSTRAINT doc_database_id_schema_name_uq UNIQUE (database_id, schema_name)
);

COMMENT ON TABLE "doc"."schema" IS 'Documentation record for a database schema.';

CREATE TABLE "doc"."table" (
    id BIGSERIAL,
    table_id BIGINT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    updated_by BIGINT,

    CONSTRAINT doc_table_pk PRIMARY KEY (id),
    CONSTRAINT doc_table_table_fk FOREIGN KEY (table_id) REFERENCES metadata."table"(id) ON DELETE CASCADE,
    CONSTRAINT doc_table_table_id_uq UNIQUE (table_id)
);

COMMENT ON TABLE "doc"."table" IS 'Documentation record for a database table.';

CREATE TABLE "doc"."column" (
    id BIGSERIAL,
    column_id BIGINT NOT NULL,
    description TEXT,
    is_pii BOOLEAN NOT NULL DEFAULT FALSE,
    sample_values TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    updated_by BIGINT,

    CONSTRAINT doc_column_pk PRIMARY KEY (id),
    CONSTRAINT doc_column_column_fk FOREIGN KEY (column_id) REFERENCES metadata."column"(id) ON DELETE CASCADE,
    CONSTRAINT doc_column_column_id_uq UNIQUE (column_id)
);

COMMENT ON TABLE "doc"."column" IS 'Documentation record for a table column. Holds descriptions, PII flags and sample values.';
COMMENT ON COLUMN "doc"."column".is_pii IS 'True when this column contains personally identifiable information (PII).';

CREATE TABLE "doc"."index" (
    id BIGSERIAL,
    index_id BIGINT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    updated_by BIGINT,

    CONSTRAINT doc_index_pk PRIMARY KEY (id),
    CONSTRAINT doc_index_index_fk FOREIGN KEY (index_id) REFERENCES metadata."index"(id) ON DELETE CASCADE,
    CONSTRAINT doc_index_index_id_uq UNIQUE (index_id)
);

COMMENT ON TABLE "doc"."index" IS 'Documentation record for a database index. Holds descriptions and metadata.';

CREATE TABLE "doc"."database_doc_tag" (
    id BIGSERIAL,
    database_doc_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_database_doc_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_database_doc_tag_database_fk FOREIGN KEY (database_doc_id) REFERENCES doc.database(id) ON DELETE CASCADE,
    CONSTRAINT doc_database_doc_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_database_doc_tag_uq UNIQUE (database_doc_id, tag_id)
);

COMMENT ON TABLE "doc"."database_doc_tag" IS 'Links metadata tags to database documentation records (doc.database).';

CREATE TABLE "doc"."schema_doc_tag" (
    id BIGSERIAL,
    schema_doc_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_schema_doc_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_schema_doc_tag_schema_fk FOREIGN KEY (schema_doc_id) REFERENCES doc.schema(id) ON DELETE CASCADE,
    CONSTRAINT doc_schema_doc_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_schema_doc_tag_uq UNIQUE (schema_doc_id, tag_id)
);

COMMENT ON TABLE "doc"."schema_doc_tag" IS 'Links metadata tags to schema documentation records (doc.schema).';

CREATE TABLE "doc"."table_doc_tag" (
    id BIGSERIAL,
    table_doc_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_table_doc_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_table_doc_tag_table_fk FOREIGN KEY (table_doc_id) REFERENCES doc."table"(id) ON DELETE CASCADE,
    CONSTRAINT doc_table_doc_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_table_doc_tag_uq UNIQUE (table_doc_id, tag_id)
);

COMMENT ON TABLE "doc"."table_doc_tag" IS 'Links metadata tags to table documentation records (doc.table).';

CREATE TABLE "doc"."column_doc_tag" (
    id BIGSERIAL,
    column_doc_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_column_doc_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_column_doc_tag_column_fk FOREIGN KEY (column_doc_id) REFERENCES doc."column"(id) ON DELETE CASCADE,
    CONSTRAINT doc_column_doc_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_column_doc_tag_uq UNIQUE (column_doc_id, tag_id)
);

COMMENT ON TABLE "doc"."column_doc_tag" IS 'Links metadata tags to column documentation records (doc.column).';

CREATE TABLE "doc"."index_doc_tag" (
    id BIGSERIAL,
    index_doc_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_index_doc_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_index_doc_tag_index_fk FOREIGN KEY (index_doc_id) REFERENCES doc."index"(id) ON DELETE CASCADE,
    CONSTRAINT doc_index_doc_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_index_doc_tag_uq UNIQUE (index_doc_id, tag_id)
);

COMMENT ON TABLE "doc"."index_doc_tag" IS 'Links metadata tags to index documentation records (doc.index).';

CREATE TABLE "doc"."database_tag" (
    id BIGSERIAL,
    database_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_database_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_database_tag_database_fk FOREIGN KEY (database_id) REFERENCES metadata.database(id) ON DELETE CASCADE,
    CONSTRAINT doc_database_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_database_tag_uq UNIQUE (database_id, tag_id)
);

COMMENT ON TABLE "doc"."database_tag" IS 'Links metadata tags directly to metadata database objects (not doc records).';

CREATE TABLE "doc"."table_tag" (
    id BIGSERIAL,
    table_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_table_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_table_tag_table_fk FOREIGN KEY (table_id) REFERENCES metadata."table"(id) ON DELETE CASCADE,
    CONSTRAINT doc_table_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_table_tag_uq UNIQUE (table_id, tag_id)
);

COMMENT ON TABLE "doc"."table_tag" IS 'Links metadata tags directly to metadata table objects (not doc records).';

CREATE TABLE "doc"."column_tag" (
    id BIGSERIAL,
    column_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_column_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_column_tag_column_fk FOREIGN KEY (column_id) REFERENCES metadata."column"(id) ON DELETE CASCADE,
    CONSTRAINT doc_column_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_column_tag_uq UNIQUE (column_id, tag_id)
);

COMMENT ON TABLE "doc"."column_tag" IS 'Links metadata tags directly to metadata column objects (not doc records).';

CREATE TABLE "doc"."index_tag" (
    id BIGSERIAL,
    index_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_index_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_index_tag_index_fk FOREIGN KEY (index_id) REFERENCES metadata."index"(id) ON DELETE CASCADE,
    CONSTRAINT doc_index_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_index_tag_uq UNIQUE (index_id, tag_id)
);

COMMENT ON TABLE "doc"."index_tag" IS 'Links metadata tags directly to metadata index objects (not doc records).';

CREATE TABLE "doc"."query_tag" (
    id BIGSERIAL,
    database_id BIGINT NOT NULL,
    query_hash TEXT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_query_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_query_tag_database_fk FOREIGN KEY (database_id) REFERENCES metadata.database(id) ON DELETE CASCADE,
    CONSTRAINT doc_query_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_query_tag_uq UNIQUE (database_id, query_hash, tag_id)
);

COMMENT ON TABLE "doc"."query_tag" IS 'Links metadata tags to native query analytics records by query hash within a database.';
