DROP TABLE metric.query_workload;
ALTER TABLE metadata."index" DROP COLUMN is_valid;
ALTER TABLE metric."table" DROP COLUMN n_tup_ins;
ALTER TABLE metric."table" DROP COLUMN n_tup_upd;
ALTER TABLE metric."table" DROP COLUMN n_tup_del;
ALTER TABLE metric."table" DROP COLUMN n_tup_hot_upd;
ALTER TABLE metric."table" DROP COLUMN stats_reset;
