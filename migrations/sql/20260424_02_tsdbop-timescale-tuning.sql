-- timescale tuning: schema fixes, chunk intervals, hypertable indexes,
-- columnstore (hypercore), retention, and chunk skipping
-- depends: 20260424_01_9UN1w-add-n-mod-since-analyze

-- -----------------------------------------------------------------------------
-- 1. Schema fixes
-- -----------------------------------------------------------------------------

-- Align metric.column.column_id with metadata.column.id (BIGINT).
ALTER TABLE "metric"."column" ALTER COLUMN column_id TYPE BIGINT;

-- Prevent duplicate collector config rows per (database_id, name) /
-- (server_id, name). Matches what the default-config triggers already produce.
ALTER TABLE "collector"."config_database"
    ADD CONSTRAINT config_database_db_name_uq UNIQUE (database_id, name);

ALTER TABLE "collector"."config_server"
    ADD CONSTRAINT config_server_server_name_uq UNIQUE (server_id, name);

-- -----------------------------------------------------------------------------
-- 2. Chunk interval tuning
--    High-frequency metric tables get 1-day chunks so each chunk roughly
--    matches a query window and stays small enough to fit hot in cache.
--    Low-frequency tables keep 7-14 day chunks to avoid excessive chunk counts.
-- -----------------------------------------------------------------------------

SELECT set_chunk_time_interval('metric.session', INTERVAL '1 day');
SELECT set_chunk_time_interval('metric.lock',    INTERVAL '1 day');
SELECT set_chunk_time_interval('metric.io',      INTERVAL '1 day');
SELECT set_chunk_time_interval('metric.cpu',     INTERVAL '1 day');
SELECT set_chunk_time_interval('metric.ram',     INTERVAL '1 day');
SELECT set_chunk_time_interval('metric.disk',    INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.table',   INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.index',   INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.column',  INTERVAL '14 days');

-- -----------------------------------------------------------------------------
-- 3. Indexes on hypertables
--    PKs already cover (collected_at, entity_id) but that leading column is
--    wrong for "last N for entity X" queries. These match the real filter shape.
-- -----------------------------------------------------------------------------

CREATE INDEX ix_metric_table_table_time   ON "metric"."table"   (table_id,    collected_at DESC);
CREATE INDEX ix_metric_index_index_time   ON "metric"."index"   (index_id,    collected_at DESC);
CREATE INDEX ix_metric_column_column_time ON "metric"."column"  (column_id,   collected_at DESC);
CREATE INDEX ix_metric_session_db_time    ON "metric"."session" (database_id, collected_at DESC);
CREATE INDEX ix_metric_lock_db_table_time ON "metric"."lock"    (database_id, table_id, collected_at DESC);
CREATE INDEX ix_metric_cpu_server_time    ON "metric"."cpu"     (server_id,   collected_at DESC);
CREATE INDEX ix_metric_ram_server_time    ON "metric"."ram"     (server_id,   collected_at DESC);
CREATE INDEX ix_metric_disk_server_time   ON "metric"."disk"    (server_id,   mount_point, collected_at DESC);
CREATE INDEX ix_metric_io_server_time     ON "metric"."io"      (server_id,   collected_at DESC);

-- -----------------------------------------------------------------------------
-- 4. Columnstore (hypercore) — modern TimescaleDB ≥ 2.18 API
--    segmentby = what queries filter by (stays uncompressed, used for lookup).
--    orderby   = time DESC → delta-encodes timestamps and enables segment
--                min/max metadata pruning.
-- -----------------------------------------------------------------------------

ALTER TABLE "metric"."session" SET (
    timescaledb.enable_columnstore = true,
    timescaledb.segmentby          = 'database_id, pid',
    timescaledb.orderby            = 'collected_at DESC'
);

ALTER TABLE "metric"."lock" SET (
    timescaledb.enable_columnstore = true,
    timescaledb.segmentby          = 'database_id, table_id',
    timescaledb.orderby            = 'collected_at DESC'
);

ALTER TABLE "metric"."table" SET (
    timescaledb.enable_columnstore = true,
    timescaledb.segmentby          = 'table_id',
    timescaledb.orderby            = 'collected_at DESC'
);

ALTER TABLE "metric"."index" SET (
    timescaledb.enable_columnstore = true,
    timescaledb.segmentby          = 'index_id',
    timescaledb.orderby            = 'collected_at DESC'
);

ALTER TABLE "metric"."column" SET (
    timescaledb.enable_columnstore = true,
    timescaledb.segmentby          = 'column_id',
    timescaledb.orderby            = 'collected_at DESC'
);

ALTER TABLE "metric"."cpu" SET (
    timescaledb.enable_columnstore = true,
    timescaledb.segmentby          = 'server_id',
    timescaledb.orderby            = 'collected_at DESC'
);

ALTER TABLE "metric"."ram" SET (
    timescaledb.enable_columnstore = true,
    timescaledb.segmentby          = 'server_id',
    timescaledb.orderby            = 'collected_at DESC'
);

ALTER TABLE "metric"."io" SET (
    timescaledb.enable_columnstore = true,
    timescaledb.segmentby          = 'server_id',
    timescaledb.orderby            = 'collected_at DESC'
);

ALTER TABLE "metric"."disk" SET (
    timescaledb.enable_columnstore = true,
    timescaledb.segmentby          = 'server_id, mount_point',
    timescaledb.orderby            = 'collected_at DESC'
);

-- Columnstore policies: move chunks older than N into columnstore form.
SELECT add_columnstore_policy('metric.session', after => INTERVAL '7 days');
SELECT add_columnstore_policy('metric.lock',    after => INTERVAL '3 days');
SELECT add_columnstore_policy('metric.io',      after => INTERVAL '3 days');
SELECT add_columnstore_policy('metric.cpu',     after => INTERVAL '7 days');
SELECT add_columnstore_policy('metric.ram',     after => INTERVAL '7 days');
SELECT add_columnstore_policy('metric.disk',    after => INTERVAL '7 days');
SELECT add_columnstore_policy('metric.table',   after => INTERVAL '7 days');
SELECT add_columnstore_policy('metric.index',   after => INTERVAL '7 days');
SELECT add_columnstore_policy('metric.column',  after => INTERVAL '7 days');

-- -----------------------------------------------------------------------------
-- 5. Retention
--    High-frequency server/session/lock data: 90 days (full quarter for
--    incident review). Metadata metrics collected every 30 min: 1 year.
-- -----------------------------------------------------------------------------

SELECT add_retention_policy('metric.session', INTERVAL '90 days');
SELECT add_retention_policy('metric.lock',    INTERVAL '90 days');
SELECT add_retention_policy('metric.io',      INTERVAL '90 days');
SELECT add_retention_policy('metric.cpu',     INTERVAL '90 days');
SELECT add_retention_policy('metric.ram',     INTERVAL '90 days');
SELECT add_retention_policy('metric.disk',    INTERVAL '1 year');
SELECT add_retention_policy('metric.table',   INTERVAL '1 year');
SELECT add_retention_policy('metric.index',   INTERVAL '1 year');
SELECT add_retention_policy('metric.column',  INTERVAL '1 year');

-- -----------------------------------------------------------------------------
-- 6. Chunk skipping (opt-in min/max tracking on non-time columns)
--    Lets the planner drop entire chunks whose [min, max] range for the
--    tracked column can't match a query predicate, before any decompression.
-- -----------------------------------------------------------------------------

SELECT enable_chunk_skipping('metric.session', 'database_id');
SELECT enable_chunk_skipping('metric.lock',    'database_id');
SELECT enable_chunk_skipping('metric.lock',    'table_id');
SELECT enable_chunk_skipping('metric.table',   'table_id');
SELECT enable_chunk_skipping('metric.index',   'index_id');
SELECT enable_chunk_skipping('metric.column',  'column_id');
SELECT enable_chunk_skipping('metric.cpu',     'server_id');
SELECT enable_chunk_skipping('metric.ram',     'server_id');
SELECT enable_chunk_skipping('metric.io',      'server_id');
SELECT enable_chunk_skipping('metric.disk',    'server_id');
