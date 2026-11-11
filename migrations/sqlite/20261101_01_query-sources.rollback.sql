DROP TRIGGER IF EXISTS sender_metric_query_workload_insert;
DROP TRIGGER default_query_workload;
DELETE FROM collector_config_database WHERE name = 'query_workload_collector';
DROP INDEX query_workload_identity_idx;
DROP INDEX query_workload_hash_idx;
ALTER TABLE metric_query_workload DROP COLUMN statement_data;
ALTER TABLE metric_query_workload DROP COLUMN user_name;
ALTER TABLE metric_query_workload DROP COLUMN query_hash;
ALTER TABLE metric_query_workload DROP COLUMN query;
