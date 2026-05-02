-- docs-tags-history
-- depends: 20260424_02_tsdbop-timescale-tuning

CREATE SCHEMA IF NOT EXISTS doc;

CREATE TABLE doc.tag (
    id          BIGSERIAL PRIMARY KEY,
    public_id   UUID NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    server_id   BIGINT NOT NULL REFERENCES collector.server(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    color       TEXT DEFAULT '#6366F1',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (server_id, name)
);

CREATE TABLE doc.database (
    id              BIGSERIAL PRIMARY KEY,
    database_id     BIGINT NOT NULL UNIQUE REFERENCES metadata.database(id) ON DELETE CASCADE,
    description     TEXT,
    owner           TEXT,
    classification  TEXT DEFAULT 'internal',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,
    updated_by      BIGINT
);

CREATE TABLE doc.schema (
    id              BIGSERIAL PRIMARY KEY,
    database_id     BIGINT NOT NULL REFERENCES metadata.database(id) ON DELETE CASCADE,
    schema_name     TEXT NOT NULL,
    description     TEXT,
    owner           TEXT,
    classification  TEXT DEFAULT 'internal',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,
    updated_by      BIGINT,
    UNIQUE (database_id, schema_name)
);

CREATE TABLE doc."table" (
    id              BIGSERIAL PRIMARY KEY,
    table_id        BIGINT NOT NULL UNIQUE REFERENCES metadata."table"(id) ON DELETE CASCADE,
    description     TEXT,
    owner           TEXT,
    classification  TEXT DEFAULT 'internal',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,
    updated_by      BIGINT
);

CREATE TABLE doc."column" (
    id              BIGSERIAL PRIMARY KEY,
    column_id       BIGINT NOT NULL UNIQUE REFERENCES metadata."column"(id) ON DELETE CASCADE,
    description     TEXT,
    is_pii          BOOLEAN NOT NULL DEFAULT FALSE,
    sample_values   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,
    updated_by      BIGINT
);

CREATE TABLE doc."index" (
    id              BIGSERIAL PRIMARY KEY,
    index_id        BIGINT NOT NULL UNIQUE REFERENCES metadata."index"(id) ON DELETE CASCADE,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,
    updated_by      BIGINT
);

CREATE TABLE doc.database_tag (
    id              BIGSERIAL PRIMARY KEY,
    database_doc_id BIGINT NOT NULL REFERENCES doc.database(id) ON DELETE CASCADE,
    tag_id          BIGINT NOT NULL REFERENCES doc.tag(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (database_doc_id, tag_id)
);

CREATE TABLE doc.schema_tag (
    id              BIGSERIAL PRIMARY KEY,
    schema_doc_id   BIGINT NOT NULL REFERENCES doc.schema(id) ON DELETE CASCADE,
    tag_id          BIGINT NOT NULL REFERENCES doc.tag(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (schema_doc_id, tag_id)
);

CREATE TABLE doc.table_tag (
    id              BIGSERIAL PRIMARY KEY,
    table_doc_id    BIGINT NOT NULL REFERENCES doc."table"(id) ON DELETE CASCADE,
    tag_id          BIGINT NOT NULL REFERENCES doc.tag(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (table_doc_id, tag_id)
);

CREATE TABLE doc.column_tag (
    id              BIGSERIAL PRIMARY KEY,
    column_doc_id   BIGINT NOT NULL REFERENCES doc."column"(id) ON DELETE CASCADE,
    tag_id          BIGINT NOT NULL REFERENCES doc.tag(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (column_doc_id, tag_id)
);

CREATE TABLE doc.index_tag (
    id              BIGSERIAL PRIMARY KEY,
    index_doc_id    BIGINT NOT NULL REFERENCES doc."index"(id) ON DELETE CASCADE,
    tag_id          BIGINT NOT NULL REFERENCES doc.tag(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (index_doc_id, tag_id)
);
