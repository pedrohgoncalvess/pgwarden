-- undo the timescale tuning migration. unwound in reverse order so the
-- columnstore disable below can actually find a hypertable with no policy
-- still attached.
-- depends: 20260424_01_9UN1w-add-n-mod-since-analyze


-- chunk skipping off

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


-- retention off

SELECT remove_retention_policy('metric.session');
SELECT remove_retention_policy('metric.lock');
SELECT remove_retention_policy('metric.io');
SELECT remove_retention_policy('metric.cpu');
SELECT remove_retention_policy('metric.ram');
SELECT remove_retention_policy('metric.disk');
SELECT remove_retention_policy('metric.table');
SELECT remove_retention_policy('metric.index');
SELECT remove_retention_policy('metric.column');


-- columnstore off. drop the policies first, then turn the feature off.
-- (disabling fails if any chunk is still in columnstore form, so on a real
-- deployment you'd need to decompress_chunk() everything first.)

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


-- indexes

DROP INDEX IF EXISTS "metric"."ix_metric_table_table_time";
DROP INDEX IF EXISTS "metric"."ix_metric_index_index_time";
DROP INDEX IF EXISTS "metric"."ix_metric_column_column_time";
DROP INDEX IF EXISTS "metric"."ix_metric_session_db_time";
DROP INDEX IF EXISTS "metric"."ix_metric_lock_db_table_time";
DROP INDEX IF EXISTS "metric"."ix_metric_cpu_server_time";
DROP INDEX IF EXISTS "metric"."ix_metric_ram_server_time";
DROP INDEX IF EXISTS "metric"."ix_metric_disk_server_time";
DROP INDEX IF EXISTS "metric"."ix_metric_io_server_time";


-- chunk intervals back to the timescale default

SELECT set_chunk_time_interval('metric.session', INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.lock',    INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.io',      INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.cpu',     INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.ram',     INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.disk',    INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.table',   INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.index',   INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.column',  INTERVAL '7 days');


-- schema nits

ALTER TABLE "collector"."config_server"
    DROP CONSTRAINT config_server_server_name_uq;

ALTER TABLE "collector"."config_database"
    DROP CONSTRAINT config_database_db_name_uq;

-- narrowing back to INTEGER is safe on a fresh install (no rows). on a real
-- deployment double-check max(column_id) < 2^31 first or this will overflow.
ALTER TABLE "metric"."column" ALTER COLUMN column_id TYPE INTEGER;
