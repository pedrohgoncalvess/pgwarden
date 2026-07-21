-- notifier module
-- depends: 20260709_01_zo2AJ-analytics-module
CREATE SCHEMA IF NOT EXISTS "notifier";

CREATE TABLE "notifier"."channel" (
    id BIGSERIAL,
    name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    credentials TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ,

    CONSTRAINT "channel_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "channel_name_uq" UNIQUE ("name")
);

COMMENT ON TABLE "notifier"."channel" IS 'Notification channels (slack, discord, teams, email). Enabled state and credentials are managed via YAML sync or the API.';
COMMENT ON COLUMN "notifier"."channel".credentials IS '[encrypted] JSON object with the channel-specific fields (webhook_url for slack/discord/teams; host, port, username, password, from, to for email).';

CREATE TABLE "notifier"."rule" (
    id BIGSERIAL,
    name TEXT NOT NULL,
    interval_seconds DOUBLE PRECISION NOT NULL DEFAULT 60,
    cooldown_seconds DOUBLE PRECISION NOT NULL DEFAULT 1800,
    window_minutes DOUBLE PRECISION NOT NULL DEFAULT 5,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ,

    CONSTRAINT "rule_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "rule_name_uq" UNIQUE ("name")
);

COMMENT ON TABLE "notifier"."rule" IS 'Central monitoring rule definition. Scope tables (rule_server, rule_database, rule_table, rule_index) attach typed targets to a rule, allowing different scheduling per group of entities.';
COMMENT ON COLUMN "notifier"."rule".interval_seconds IS 'Seconds between evaluations of this rule.';
COMMENT ON COLUMN "notifier"."rule".cooldown_seconds IS 'Minimum seconds between repeated alerts for the same target+entity+severity.';
COMMENT ON COLUMN "notifier"."rule".window_minutes IS 'Data window considered in each evaluation.';

CREATE TABLE "notifier"."rule_server" (
    id BIGSERIAL,
    rule_id BIGINT NOT NULL,
    server_id BIGINT,
    type TEXT NOT NULL,
    warning DOUBLE PRECISION NOT NULL,
    critical DOUBLE PRECISION NOT NULL,
    direction TEXT NOT NULL DEFAULT 'above',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT "rule_server_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "rule_server_rule_fk" FOREIGN KEY ("rule_id") REFERENCES "notifier"."rule" ("id") ON DELETE CASCADE,
    CONSTRAINT "rule_server_server_fk" FOREIGN KEY ("server_id") REFERENCES "collector"."server" ("id") ON DELETE CASCADE,
    CONSTRAINT "rule_server_type_ck" CHECK ("type" IN ('cpu_percent', 'ram_percent', 'disk_percent')),
    CONSTRAINT "rule_server_direction_ck" CHECK ("direction" IN ('above', 'below')),
    CONSTRAINT "rule_server_uq" UNIQUE NULLS NOT DISTINCT ("rule_id", "type", "server_id")
);

COMMENT ON TABLE "notifier"."rule_server" IS 'Server-scope alert targets (cpu, ram, disk). NULL server_id means all servers.';

CREATE TABLE "notifier"."rule_database" (
    id BIGSERIAL,
    rule_id BIGINT NOT NULL,
    database_id BIGINT,
    type TEXT NOT NULL,
    warning DOUBLE PRECISION NOT NULL,
    critical DOUBLE PRECISION NOT NULL,
    direction TEXT NOT NULL DEFAULT 'above',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT "rule_database_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "rule_database_rule_fk" FOREIGN KEY ("rule_id") REFERENCES "notifier"."rule" ("id") ON DELETE CASCADE,
    CONSTRAINT "rule_database_database_fk" FOREIGN KEY ("database_id") REFERENCES "metadata"."database" ("id") ON DELETE CASCADE,
    CONSTRAINT "rule_database_type_ck" CHECK ("type" IN (
        'growth_percent', 'cache_hit_ratio', 'deadlocks', 'tup_updated', 'tup_deleted',
        'long_query_ms', 'waiting_sessions', 'blocked_locks',
        'table_created', 'table_dropped', 'index_created', 'index_dropped'
    )),
    CONSTRAINT "rule_database_direction_ck" CHECK ("direction" IN ('above', 'below')),
    CONSTRAINT "rule_database_uq" UNIQUE NULLS NOT DISTINCT ("rule_id", "type", "database_id")
);

COMMENT ON TABLE "notifier"."rule_database" IS 'Database-scope alert targets (growth, cache hit ratio, deadlocks, update/delete volume, sessions, locks, schema changes). NULL database_id means all databases.';

CREATE TABLE "notifier"."rule_table" (
    id BIGSERIAL,
    rule_id BIGINT NOT NULL,
    table_id BIGINT,
    type TEXT NOT NULL,
    warning DOUBLE PRECISION NOT NULL,
    critical DOUBLE PRECISION NOT NULL,
    direction TEXT NOT NULL DEFAULT 'above',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT "rule_table_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "rule_table_rule_fk" FOREIGN KEY ("rule_id") REFERENCES "notifier"."rule" ("id") ON DELETE CASCADE,
    CONSTRAINT "rule_table_table_fk" FOREIGN KEY ("table_id") REFERENCES "metadata"."table" ("id") ON DELETE CASCADE,
    CONSTRAINT "rule_table_type_ck" CHECK ("type" IN (
        'growth_percent', 'dead_tuples', 'dead_tuple_ratio',
        'column_added', 'update_delete_queries', 'bloating'
    )),
    CONSTRAINT "rule_table_direction_ck" CHECK ("direction" IN ('above', 'below')),
    CONSTRAINT "rule_table_uq" UNIQUE NULLS NOT DISTINCT ("rule_id", "type", "table_id")
);

COMMENT ON TABLE "notifier"."rule_table" IS 'Table-scope alert targets (growth, dead tuples, column additions, update/delete queries, bloating). NULL table_id means all tables.';

CREATE TABLE "notifier"."rule_index" (
    id BIGSERIAL,
    rule_id BIGINT NOT NULL,
    index_id BIGINT,
    type TEXT NOT NULL,
    warning DOUBLE PRECISION NOT NULL,
    critical DOUBLE PRECISION NOT NULL,
    direction TEXT NOT NULL DEFAULT 'above',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT "rule_index_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "rule_index_rule_fk" FOREIGN KEY ("rule_id") REFERENCES "notifier"."rule" ("id") ON DELETE CASCADE,
    CONSTRAINT "rule_index_index_fk" FOREIGN KEY ("index_id") REFERENCES "metadata"."index" ("id") ON DELETE CASCADE,
    CONSTRAINT "rule_index_type_ck" CHECK ("type" IN ('hit_rate')),
    CONSTRAINT "rule_index_direction_ck" CHECK ("direction" IN ('above', 'below')),
    CONSTRAINT "rule_index_uq" UNIQUE NULLS NOT DISTINCT ("rule_id", "type", "index_id")
);

COMMENT ON TABLE "notifier"."rule_index" IS 'Index-scope alert targets (hit rate). NULL index_id means all indexes.';

CREATE TABLE "notifier"."notification" (
    id BIGSERIAL,
    message TEXT NOT NULL,
    hidden BOOLEAN NOT NULL DEFAULT FALSE,
    params JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT "notification_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "notification_created_at_idx" ON "notifier"."notification" ("created_at" DESC);
CREATE INDEX "notification_hidden_idx" ON "notifier"."notification" ("hidden") WHERE NOT "hidden";

COMMENT ON TABLE "notifier"."notification" IS 'Fired alerts shown in the frontend notification center. params carries navigation data (path, entity ids, time filter) to deep-link into the relevant page.';
COMMENT ON COLUMN "notifier"."notification".params IS 'JSON object with path (relative route), scope, type, entity ids, severity, value, threshold and the from/to time filter of the alert.';
