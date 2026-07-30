-- depends: 20260424_02_tsdbop-timescale-tuning

CREATE SCHEMA IF NOT EXISTS doc;
CREATE SCHEMA IF NOT EXISTS base;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;

CREATE TABLE IF NOT EXISTS "base"."embedding_cache" (
    id BIGSERIAL,
    term TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT embedding_cache_pk PRIMARY KEY (id),
    CONSTRAINT embedding_cache_term_uq UNIQUE (term)
);

CREATE TABLE "doc"."tag" (
    id BIGSERIAL,
    public_id UUID NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    server_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    color TEXT DEFAULT '#07a96e',
    type VARCHAR(20) NOT NULL DEFAULT 'default',
    embedding vector(1024),

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
    embedding vector(1024),
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
    embedding vector(1024),
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
    embedding vector(1024),
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
    embedding vector(1024),
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
    embedding vector(1024),
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

CREATE INDEX IF NOT EXISTS doc_database_embedding_idx ON doc.database USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS doc_schema_embedding_idx ON doc.schema USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS doc_table_embedding_idx ON doc."table" USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS doc_column_embedding_idx ON doc."column" USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS doc_index_embedding_idx ON doc."index" USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS doc_tag_embedding_idx ON doc.tag USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS embedding_cache_embedding_idx ON base.embedding_cache USING hnsw (embedding vector_cosine_ops);

-- Immutable user-facing activity history for documentation and tag changes.
CREATE TABLE "doc"."activity_history" (
    id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL REFERENCES metadata.database(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('documentation', 'tag')),
    action TEXT NOT NULL CHECK (action IN ('created', 'updated', 'assigned', 'unassigned')),
    target_type TEXT NOT NULL,
    target_id BIGINT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_activity_history_database_occurred ON doc.activity_history (database_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION doc.fn_activity_history()
RETURNS TRIGGER AS $$
DECLARE
    payload JSONB;
    target BIGINT;
    db_id BIGINT;
    kind TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN payload := to_jsonb(OLD); ELSE payload := to_jsonb(NEW); END IF;
    kind := replace(TG_TABLE_NAME, '_doc_tag', '');
    kind := replace(kind, '_tag', '');
    IF TG_TABLE_NAME = 'database' THEN db_id := (payload->>'database_id')::bigint; target := db_id;
    ELSIF TG_TABLE_NAME = 'schema' THEN db_id := (payload->>'database_id')::bigint;
    ELSIF TG_TABLE_NAME = 'table' THEN
        target := (payload->>'table_id')::bigint;
        SELECT database_id INTO db_id FROM metadata."table" WHERE id = target;
    ELSIF TG_TABLE_NAME = 'column' THEN
        target := (payload->>'column_id')::bigint;
        SELECT t.database_id INTO db_id FROM metadata."column" c JOIN metadata."table" t ON t.id = c.table_id WHERE c.id = target;
    ELSIF TG_TABLE_NAME = 'index' THEN
        target := (payload->>'index_id')::bigint;
        SELECT t.database_id INTO db_id FROM metadata."index" i JOIN metadata."table" t ON t.id = i.table_id WHERE i.id = target;
    ELSE
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END IF;
    INSERT INTO doc.activity_history (database_id, event_type, action, target_type, target_id, details)
    VALUES (db_id, CASE WHEN TG_TABLE_NAME IN ('database','schema','table','column','index') THEN 'documentation' ELSE 'tag' END,
        CASE WHEN TG_OP = 'INSERT' THEN CASE WHEN TG_TABLE_NAME IN ('database','schema','table','column','index') THEN 'created' ELSE 'assigned' END
             WHEN TG_OP = 'UPDATE' THEN 'updated' ELSE 'unassigned' END,
        kind, target, payload);
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_activity_database AFTER INSERT OR UPDATE OR DELETE ON doc.database FOR EACH ROW EXECUTE FUNCTION doc.fn_activity_history();
CREATE TRIGGER trg_activity_schema AFTER INSERT OR UPDATE OR DELETE ON doc.schema FOR EACH ROW EXECUTE FUNCTION doc.fn_activity_history();
CREATE TRIGGER trg_activity_table AFTER INSERT OR UPDATE OR DELETE ON doc."table" FOR EACH ROW EXECUTE FUNCTION doc.fn_activity_history();
CREATE TRIGGER trg_activity_column AFTER INSERT OR UPDATE OR DELETE ON doc.column FOR EACH ROW EXECUTE FUNCTION doc.fn_activity_history();
CREATE TRIGGER trg_activity_index AFTER INSERT OR UPDATE OR DELETE ON doc.index FOR EACH ROW EXECUTE FUNCTION doc.fn_activity_history();

CREATE OR REPLACE FUNCTION doc.fn_tag_activity_history()
RETURNS TRIGGER AS $$
DECLARE
    payload JSONB;
    db_id BIGINT;
    target BIGINT;
    target_kind TEXT;
    tag_label TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN payload := to_jsonb(OLD); ELSE payload := to_jsonb(NEW); END IF;
    SELECT name INTO tag_label FROM doc.tag WHERE id = (payload->>'tag_id')::bigint;

    CASE TG_TABLE_NAME
        WHEN 'database_tag' THEN
            db_id := (payload->>'database_id')::bigint; target := db_id; target_kind := 'database';
        WHEN 'table_tag' THEN
            target := (payload->>'table_id')::bigint; target_kind := 'table';
            SELECT database_id INTO db_id FROM metadata."table" WHERE id = target;
        WHEN 'column_tag' THEN
            target := (payload->>'column_id')::bigint; target_kind := 'column';
            SELECT t.database_id INTO db_id FROM metadata."column" c JOIN metadata."table" t ON t.id = c.table_id WHERE c.id = target;
        WHEN 'index_tag' THEN
            target := (payload->>'index_id')::bigint; target_kind := 'index';
            SELECT t.database_id INTO db_id FROM metadata."index" i JOIN metadata."table" t ON t.id = i.table_id WHERE i.id = target;
        WHEN 'query_tag' THEN
            db_id := (payload->>'database_id')::bigint; target_kind := 'native_query';
        WHEN 'database_doc_tag' THEN
            target_kind := 'database';
            SELECT database_id, database_id INTO db_id, target FROM doc.database WHERE id = (payload->>'database_doc_id')::bigint;
        WHEN 'schema_doc_tag' THEN
            target_kind := 'schema';
            SELECT database_id INTO db_id FROM doc.schema WHERE id = (payload->>'schema_doc_id')::bigint;
        WHEN 'table_doc_tag' THEN
            target_kind := 'table';
            SELECT d.table_id, t.database_id INTO target, db_id FROM doc."table" d JOIN metadata."table" t ON t.id = d.table_id WHERE d.id = (payload->>'table_doc_id')::bigint;
        WHEN 'column_doc_tag' THEN
            target_kind := 'column';
            SELECT d.column_id, t.database_id INTO target, db_id FROM doc.column d JOIN metadata."column" c ON c.id = d.column_id JOIN metadata."table" t ON t.id = c.table_id WHERE d.id = (payload->>'column_doc_id')::bigint;
        WHEN 'index_doc_tag' THEN
            target_kind := 'index';
            SELECT d.index_id, t.database_id INTO target, db_id FROM doc.index d JOIN metadata."index" i ON i.id = d.index_id JOIN metadata."table" t ON t.id = i.table_id WHERE d.id = (payload->>'index_doc_id')::bigint;
    END CASE;
    INSERT INTO doc.activity_history (database_id, event_type, action, target_type, target_id, details)
    VALUES (db_id, 'tag', CASE WHEN TG_OP = 'INSERT' THEN 'assigned' ELSE 'unassigned' END,
            target_kind, target, jsonb_build_object('tag_id', payload->>'tag_id', 'tag_name', tag_label));
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_activity_database_tag AFTER INSERT OR DELETE ON doc.database_tag FOR EACH ROW EXECUTE FUNCTION doc.fn_tag_activity_history();
CREATE TRIGGER trg_activity_table_tag AFTER INSERT OR DELETE ON doc.table_tag FOR EACH ROW EXECUTE FUNCTION doc.fn_tag_activity_history();
CREATE TRIGGER trg_activity_column_tag AFTER INSERT OR DELETE ON doc.column_tag FOR EACH ROW EXECUTE FUNCTION doc.fn_tag_activity_history();
CREATE TRIGGER trg_activity_index_tag AFTER INSERT OR DELETE ON doc.index_tag FOR EACH ROW EXECUTE FUNCTION doc.fn_tag_activity_history();
CREATE TRIGGER trg_activity_query_tag AFTER INSERT OR DELETE ON doc.query_tag FOR EACH ROW EXECUTE FUNCTION doc.fn_tag_activity_history();
CREATE TRIGGER trg_activity_database_doc_tag AFTER INSERT OR DELETE ON doc.database_doc_tag FOR EACH ROW EXECUTE FUNCTION doc.fn_tag_activity_history();
CREATE TRIGGER trg_activity_schema_doc_tag AFTER INSERT OR DELETE ON doc.schema_doc_tag FOR EACH ROW EXECUTE FUNCTION doc.fn_tag_activity_history();
CREATE TRIGGER trg_activity_table_doc_tag AFTER INSERT OR DELETE ON doc.table_doc_tag FOR EACH ROW EXECUTE FUNCTION doc.fn_tag_activity_history();
CREATE TRIGGER trg_activity_column_doc_tag AFTER INSERT OR DELETE ON doc.column_doc_tag FOR EACH ROW EXECUTE FUNCTION doc.fn_tag_activity_history();
CREATE TRIGGER trg_activity_index_doc_tag AFTER INSERT OR DELETE ON doc.index_doc_tag FOR EACH ROW EXECUTE FUNCTION doc.fn_tag_activity_history();
