-- analytics module
-- depends: 20260623_01_database-stats-metric  20260624_01_native-query-metric  20260627_01_schema-index-history  20260706_01_embeddings-doc-and-tags
CREATE SCHEMA IF NOT EXISTS "analytics";

CREATE TABLE "analytics"."query"(
    id BIGSERIAL,
    database_id BIGINT NOT NULL,
    query TEXT NOT NULL UNIQUE,
    user_name TEXT,
    application_name TEXT,
    hash TEXT NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    CONSTRAINT "query_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "analytics"."query_column_hit"(
    id BIGSERIAL,
    query_id INTEGER NOT NULL,
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    is_selected BOOLEAN DEFAULT FALSE NOT NULL,
    is_condition BOOLEAN DEFAULT FALSE NOT NULL,
    is_condition_foreign BOOLEAN DEFAULT FALSE NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    CONSTRAINT "query_column_hit_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "query_column_hit_query_fkey" FOREIGN KEY ("query_id") REFERENCES "analytics"."query" ("id") ON DELETE CASCADE
);

CREATE TABLE "analytics"."query_table_hit"(
    id BIGSERIAL,
    query_id INTEGER NOT NULL,
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    alias TEXT,
    is_foreign BOOLEAN DEFAULT FALSE NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    CONSTRAINT "query_table_hit_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "query_table_hit_query_fkey" FOREIGN KEY ("query_id") REFERENCES "analytics"."query" ("id") ON DELETE CASCADE
);

CREATE INDEX "query_column_hit_query_idx" ON "analytics"."query_column_hit" ("query_id");
CREATE INDEX "query_table_hit_query_idx" ON "analytics"."query_table_hit" ("query_id");
