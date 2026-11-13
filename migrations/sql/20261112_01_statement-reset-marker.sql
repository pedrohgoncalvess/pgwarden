-- depends: 20261101_01_query-sources

-- Compute the entry reset marker once on ingestion instead of parsing every
-- retained JSON payload on each analytics request.
ALTER TABLE metric.query_workload
    ADD COLUMN IF NOT EXISTS statement_stats_since TEXT;

CREATE FUNCTION metric.set_statement_reset_marker() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.statement_stats_since := COALESCE(
        (NEW.statement_data::json -> 'stats_since')::text, 'null'
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER statement_reset_marker
    BEFORE INSERT OR UPDATE OF statement_data ON metric.query_workload
    FOR EACH ROW EXECUTE FUNCTION metric.set_statement_reset_marker();

CREATE INDEX IF NOT EXISTS query_workload_window_idx
    ON metric.query_workload(database_id, query_id, user_id, is_toplevel, collected_at);
