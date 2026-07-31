-- depends: 20260623_01_database-stats-metric  20260624_01_native-query-metric  20260627_01_schema-index-history  20260425_02_docs-tags-history
CREATE SCHEMA IF NOT EXISTS "analytics";

CREATE TABLE "analytics"."query"(
    id BIGSERIAL,
    database_id BIGINT NOT NULL,
    query TEXT NOT NULL,
    user_name TEXT,
    application_name TEXT,
    hash TEXT NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    CONSTRAINT "query_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "query_database_query_key" UNIQUE ("database_id", "query")
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

CREATE TABLE "analytics"."config" (
    id BIGSERIAL,
    database_id BIGINT NOT NULL,
    run_interval INTEGER NOT NULL DEFAULT 1800,
    last_seen TIMESTAMPTZ,
    query_analytics_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    recommendation_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT "config_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "config_database_key" UNIQUE ("database_id"),
    CONSTRAINT "config_run_interval_min" CHECK ("run_interval" >= 10),
    CONSTRAINT "config_database_fkey" FOREIGN KEY ("database_id") REFERENCES "metadata"."database" ("id") ON DELETE CASCADE
);

CREATE TABLE "analytics"."run" (
    id BIGSERIAL,
    database_id BIGINT NOT NULL,
    run_at TIMESTAMPTZ NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT "run_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "run_database_fkey" FOREIGN KEY ("database_id") REFERENCES "metadata"."database" ("id") ON DELETE CASCADE
);

CREATE INDEX "run_database_created_idx" ON "analytics"."run" ("database_id", "created_at");

CREATE TABLE "analytics"."query_analysis" (
    id BIGSERIAL,
    run_id BIGINT NOT NULL,
    query_id BIGINT NOT NULL,
    database_id BIGINT NOT NULL,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_ms DOUBLE PRECISION,
    overall_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    summary TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT "query_analysis_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "query_analysis_run_fkey" FOREIGN KEY ("run_id") REFERENCES "analytics"."run" ("id") ON DELETE CASCADE,
    CONSTRAINT "query_analysis_query_fkey" FOREIGN KEY ("query_id") REFERENCES "analytics"."query" ("id") ON DELETE CASCADE,
    CONSTRAINT "query_analysis_database_fkey" FOREIGN KEY ("database_id") REFERENCES "metadata"."database" ("id") ON DELETE CASCADE
);

CREATE INDEX "query_analysis_query_idx" ON "analytics"."query_analysis" ("query_id");
CREATE INDEX "query_analysis_run_idx" ON "analytics"."query_analysis" ("run_id");

CREATE TABLE "analytics"."query_analysis_finding" (
    id BIGSERIAL,
    analysis_id BIGINT NOT NULL,
    type TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    title TEXT NOT NULL,
    explanation TEXT NOT NULL,
    recommendation TEXT,
    evidence JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT "query_analysis_finding_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "query_analysis_finding_analysis_fkey" FOREIGN KEY ("analysis_id") REFERENCES "analytics"."query_analysis" ("id") ON DELETE CASCADE
);

CREATE INDEX "query_analysis_finding_analysis_idx" ON "analytics"."query_analysis_finding" ("analysis_id");
CREATE INDEX "query_analysis_finding_type_idx" ON "analytics"."query_analysis_finding" ("type");

CREATE INDEX "native_query_database_user_collected_idx"
    ON "metric"."native_query" (database_id, user_name, collected_at DESC);

CREATE INDEX "native_query_database_app_collected_idx"
    ON "metric"."native_query" (database_id, application_name, collected_at DESC);

CREATE INDEX "native_query_database_queryhash_collected_idx"
    ON "metric"."native_query" (database_id, query_hash, collected_at DESC);
