-- rollback of timescale tuning migration
-- depends: 20260424_01_9UN1w-add-n-mod-since-analyze

-- -----------------------------------------------------------------------------
-- 6. Chunk skipping
-- -----------------------------------------------------------------------------

SELECT disable_chunk_skipping('metric.session', 'database_id');
SELECT disable_chunk_skipping('metric.lock',    'database_id');
SELECT disable_chunk_skipping('metric.lock',    'table_id');
SELECT disable_chunk_skipping('metric.table',   'table_id');
SELECT disable_chunk_skipping('metric.index',   'index_id');
SELECT disable_chunk_skipping('metric.column',  'column_id');
SELECT disable_chunk_skipping('metric.cpu',     'server_id');
SELECT disable_chunk_skipping('metric.ram',     'server_id');
SELECT disable_chunk_skipping('metric.io',      'server_id');
SELECT disable_chunk_skipping('metric.disk',    'server_id');

-- -----------------------------------------------------------------------------
-- 5. Retention policies
-- -----------------------------------------------------------------------------

SELECT remove_retention_policy('metric.session');
SELECT remove_retention_policy('metric.lock');
SELECT remove_retention_policy('metric.io');
SELECT remove_retention_policy('metric.cpu');
SELECT remove_retention_policy('metric.ram');
SELECT remove_retention_policy('metric.disk');
SELECT remove_retention_policy('metric.table');
SELECT remove_retention_policy('metric.index');
SELECT remove_retention_policy('metric.column');

-- -----------------------------------------------------------------------------
-- 4. Columnstore policies and settings
--    Policies must be removed first; disabling columnstore requires all
--    chunks on the hypertable to be in rowstore form.
-- -----------------------------------------------------------------------------

SELECT remove_columnstore_policy('metric.session');
SELECT remove_columnstore_policy('metric.lock');
SELECT remove_columnstore_policy('metric.io');
SELECT remove_columnstore_policy('metric.cpu');
SELECT remove_columnstore_policy('metric.ram');
SELECT remove_columnstore_policy('metric.disk');
SELECT remove_columnstore_policy('metric.table');
SELECT remove_columnstore_policy('metric.index');
SELECT remove_columnstore_policy('metric.column');

ALTER TABLE "metric"."session" SET (timescaledb.enable_columnstore = false);
ALTER TABLE "metric"."lock"    SET (timescaledb.enable_columnstore = false);
ALTER TABLE "metric"."table"   SET (timescaledb.enable_columnstore = false);
ALTER TABLE "metric"."index"   SET (timescaledb.enable_columnstore = false);
ALTER TABLE "metric"."column"  SET (timescaledb.enable_columnstore = false);
ALTER TABLE "metric"."cpu"     SET (timescaledb.enable_columnstore = false);
ALTER TABLE "metric"."ram"     SET (timescaledb.enable_columnstore = false);
ALTER TABLE "metric"."io"      SET (timescaledb.enable_columnstore = false);
ALTER TABLE "metric"."disk"    SET (timescaledb.enable_columnstore = false);

-- -----------------------------------------------------------------------------
-- 3. Indexes
-- -----------------------------------------------------------------------------

DROP INDEX IF EXISTS "metric"."ix_metric_table_table_time";
DROP INDEX IF EXISTS "metric"."ix_metric_index_index_time";
DROP INDEX IF EXISTS "metric"."ix_metric_column_column_time";
DROP INDEX IF EXISTS "metric"."ix_metric_session_db_time";
DROP INDEX IF EXISTS "metric"."ix_metric_lock_db_table_time";
DROP INDEX IF EXISTS "metric"."ix_metric_cpu_server_time";
DROP INDEX IF EXISTS "metric"."ix_metric_ram_server_time";
DROP INDEX IF EXISTS "metric"."ix_metric_disk_server_time";
DROP INDEX IF EXISTS "metric"."ix_metric_io_server_time";

-- -----------------------------------------------------------------------------
-- 2. Chunk interval tuning — revert to the TimescaleDB default (7 days)
-- -----------------------------------------------------------------------------

SELECT set_chunk_time_interval('metric.session', INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.lock',    INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.io',      INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.cpu',     INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.ram',     INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.disk',    INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.table',   INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.index',   INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.column',  INTERVAL '7 days');

-- -----------------------------------------------------------------------------
-- 1. Schema fixes
-- -----------------------------------------------------------------------------

ALTER TABLE "collector"."config_server"
    DROP CONSTRAINT config_server_server_name_uq;

ALTER TABLE "collector"."config_database"
    DROP CONSTRAINT config_database_db_name_uq;

-- Narrowing BIGINT back to INTEGER is only safe while no column_id value
-- exceeds 2^31 - 1. Fresh installs are empty, so this is a no-op there;
-- any deployment with real data should audit first.
ALTER TABLE "metric"."column" ALTER COLUMN column_id TYPE INTEGER;
