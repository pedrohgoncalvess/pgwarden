-- add n_mod_since_analyze
-- depends: 20260408_01_vVWWG-api-migrations

ALTER TABLE "metric"."table" ADD COLUMN modifications_since_last_analyze BIGINT;
COMMENT ON COLUMN "metric"."table".modifications_since_last_analyze IS 'Number of modifications since the last analyze (n_mod_since_analyze from pg_stat_user_tables).';
