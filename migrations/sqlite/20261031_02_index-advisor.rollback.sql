DROP TABLE metric_query_workload;
ALTER TABLE metadata_index DROP COLUMN is_valid;
ALTER TABLE metric_table DROP COLUMN n_tup_ins;
ALTER TABLE metric_table DROP COLUMN n_tup_upd;
ALTER TABLE metric_table DROP COLUMN n_tup_del;
ALTER TABLE metric_table DROP COLUMN n_tup_hot_upd;
ALTER TABLE metric_table DROP COLUMN stats_reset;
