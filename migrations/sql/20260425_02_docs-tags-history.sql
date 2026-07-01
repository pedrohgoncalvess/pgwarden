-- docs-tags-history
-- depends: 20260424_02_tsdbop-timescale-tuning

CREATE SCHEMA IF NOT EXISTS doc;

CREATE TABLE "doc"."tag" (
    id BIGSERIAL,
    public_id UUID NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    color TEXT DEFAULT '#6366F1',
    type VARCHAR(20) NOT NULL DEFAULT 'default',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_tag_pk PRIMARY KEY (id)
);

CREATE TABLE "doc"."database" (
    id BIGSERIAL,
    database_id BIGINT NOT NULL,
    description TEXT,
    owner TEXT,
    classification TEXT DEFAULT 'internal',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    updated_by BIGINT,

    CONSTRAINT doc_database_pk PRIMARY KEY (id),
    CONSTRAINT doc_database_database_fk FOREIGN KEY (database_id) REFERENCES metadata.database(id) ON DELETE CASCADE
);

CREATE TABLE "doc"."schema" (
    id BIGSERIAL,
    database_id BIGINT NOT NULL,
    schema_name TEXT NOT NULL,
    description TEXT,
    owner TEXT,
    classification TEXT DEFAULT 'internal',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    updated_by BIGINT,

    CONSTRAINT doc_schema_pk PRIMARY KEY (id),
    CONSTRAINT doc_schema_database_fk FOREIGN KEY (database_id) REFERENCES metadata.database(id) ON DELETE CASCADE,
    CONSTRAINT doc_database_id_schema_name_uq UNIQUE (database_id, schema_name)
);

CREATE TABLE "doc"."table" (
    id BIGSERIAL,
    table_id BIGINT NOT NULL,
    description TEXT,
    owner TEXT,
    classification TEXT DEFAULT 'internal',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    updated_by BIGINT,

    CONSTRAINT doc_table_pk PRIMARY KEY (id),
    CONSTRAINT doc_table_table_fk FOREIGN KEY (table_id) REFERENCES metadata."table"(id) ON DELETE CASCADE,
    CONSTRAINT doc_table_table_id_uq UNIQUE (table_id)
);

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

CREATE TABLE "doc"."database_tag" (
    id BIGSERIAL,
    database_doc_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_database_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_database_tag_database_fk FOREIGN KEY (database_doc_id) REFERENCES doc.database(id) ON DELETE CASCADE,
    CONSTRAINT doc_database_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_database_tag_uq UNIQUE (database_doc_id, tag_id)
);

CREATE TABLE "doc"."schema_tag" (
    id BIGSERIAL,
    schema_doc_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_schema_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_schema_tag_schema_fk FOREIGN KEY (schema_doc_id) REFERENCES doc.schema(id) ON DELETE CASCADE,
    CONSTRAINT doc_schema_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_schema_tag_uq UNIQUE (schema_doc_id, tag_id)
);

CREATE TABLE "doc"."table_tag" (
    id BIGSERIAL,
    table_doc_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_table_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_table_tag_table_fk FOREIGN KEY (table_doc_id) REFERENCES doc."table"(id) ON DELETE CASCADE,
    CONSTRAINT doc_table_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_table_tag_uq UNIQUE (table_doc_id, tag_id)
);

CREATE TABLE "doc"."column_tag" (
    id BIGSERIAL,
    column_doc_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_column_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_column_tag_column_fk FOREIGN KEY (column_doc_id) REFERENCES doc."column"(id) ON DELETE CASCADE,
    CONSTRAINT doc_column_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_column_tag_uq UNIQUE (column_doc_id, tag_id)
);

CREATE TABLE "doc"."index_tag" (
    id BIGSERIAL,
    index_doc_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_index_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_index_tag_index_fk FOREIGN KEY (index_doc_id) REFERENCES doc."index"(id) ON DELETE CASCADE,
    CONSTRAINT doc_index_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_index_tag_uq UNIQUE (index_doc_id, tag_id)
);

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

CREATE TABLE "doc"."query_tag" (
    id BIGSERIAL,
    database_id BIGINT NOT NULL,
    query_hash TEXT NOT NULL,
    tag_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT doc_native_query_tag_pk PRIMARY KEY (id),
    CONSTRAINT doc_native_query_tag_database_fk FOREIGN KEY (database_id) REFERENCES metadata.database(id) ON DELETE CASCADE,
    CONSTRAINT doc_native_query_tag_tag_fk FOREIGN KEY (tag_id) REFERENCES doc.tag(id) ON DELETE CASCADE,
    CONSTRAINT doc_native_query_tag_uq UNIQUE (database_id, query_hash, tag_id)
);
