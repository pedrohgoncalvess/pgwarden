DROP INDEX IF EXISTS metric.query_workload_window_idx;
DROP TRIGGER statement_reset_marker ON metric.query_workload;
DROP FUNCTION metric.set_statement_reset_marker();
ALTER TABLE metric.query_workload DROP COLUMN statement_stats_since;
