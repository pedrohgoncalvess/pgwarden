-- Optimize query analytics filters on native_query metric table.

CREATE INDEX native_query_database_user_collected_idx
    ON "metric"."native_query" (database_id, user_name, collected_at DESC);

CREATE INDEX native_query_database_app_collected_idx
    ON "metric"."native_query" (database_id, application_name, collected_at DESC);

CREATE INDEX native_query_database_queryhash_collected_idx
    ON "metric"."native_query" (database_id, query_hash, collected_at DESC);
