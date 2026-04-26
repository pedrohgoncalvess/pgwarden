-- timescale tuning: chunk intervals, indexes, columnstore, retention,
-- chunk skipping, plus a few schema nits I noticed along the way.
-- depends: 20260424_01_9UN1w-add-n-mod-since-analyze


-- schema nits ----------------------------------------------------------------

-- column_id was INTEGER while metadata.column.id is BIGINT. mismatched FK
-- types work but it's a footgun, so widen it.
ALTER TABLE "metric"."column" ALTER COLUMN column_id TYPE BIGINT;

-- the default-config triggers always insert one row per (database_id, name)
-- and (server_id, name) -- nothing was actually enforcing it though, so a
-- second trigger run would happily duplicate everything. add the constraint.
ALTER TABLE "collector"."config_database"
    ADD CONSTRAINT config_database_db_name_uq UNIQUE (database_id, name);

ALTER TABLE "collector"."config_server"
    ADD CONSTRAINT config_server_server_name_uq UNIQUE (server_id, name);


-- chunk intervals ------------------------------------------------------------
-- default is 7 days for everything, which is way too coarse for the 3-5s
-- collectors. rule of thumb: a chunk should fit in roughly 25% of RAM and
-- match a typical query window. 1 day for the hot stuff, longer for the
-- once-every-30-min metadata metrics.

SELECT set_chunk_time_interval('metric.session', INTERVAL '1 day');
SELECT set_chunk_time_interval('metric.lock',    INTERVAL '1 day');
SELECT set_chunk_time_interval('metric.io',      INTERVAL '1 day');
SELECT set_chunk_time_interval('metric.cpu',     INTERVAL '1 day');
SELECT set_chunk_time_interval('metric.ram',     INTERVAL '1 day');
SELECT set_chunk_time_interval('metric.disk',    INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.table',   INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.index',   INTERVAL '7 days');
SELECT set_chunk_time_interval('metric.column',  INTERVAL '14 days');


-- indexes --------------------------------------------------------------------
-- the PKs are (collected_at, entity_id) which works for uniqueness guarantees
-- but is the wrong way round for day-to-day queries like
-- "show me the last hour for server X". flip it.

CREATE INDEX ix_metric_table_table_time   ON "metric"."table"   (table_id,    collected_at DESC);
CREATE INDEX ix_metric_index_index_time   ON "metric"."index"   (index_id,    collected_at DESC);
CREATE INDEX ix_metric_column_column_time ON "metric"."column"  (column_id,   collected_at DESC);
CREATE INDEX ix_metric_session_db_time    ON "metric"."session" (database_id, collected_at DESC);
CREATE INDEX ix_metric_lock_db_table_time ON "metric"."lock"    (database_id, table_id, collected_at DESC);
CREATE INDEX ix_metric_cpu_server_time    ON "metric"."cpu"     (server_id,   collected_at DESC);
CREATE INDEX ix_metric_ram_server_time    ON "metric"."ram"     (server_id,   collected_at DESC);
CREATE INDEX ix_metric_disk_server_time   ON "metric"."disk"    (server_id,   mount_point, collected_at DESC);
CREATE INDEX ix_metric_io_server_time     ON "metric"."io"      (server_id,   collected_at DESC);


-- columnstore (hypercore) ----------------------------------------------------
-- without compression we'd be using timescale as fancy partitioned postgres.
-- segmentby = whatever queries filter by (it stays uncompressed and acts as
-- an sparse index under a chunk/partition). orderby = collected_at DESC so timestamps
-- delta-encode well and we get free min/max metadata for chunk pruning.
-- needs timescaledb >= 2.18 for the columnstore api; the legacy
-- timescaledb.compress / add_compression_policy form is deprecated.

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

-- and the policies that actually run the conversion to column store form. lock/io are converted
-- after 3 days because they're the chattiest; the rest can wait a week.
SELECT add_columnstore_policy('metric.session', after => INTERVAL '7 days');
SELECT add_columnstore_policy('metric.lock',    after => INTERVAL '3 days');
SELECT add_columnstore_policy('metric.io',      after => INTERVAL '3 days');
SELECT add_columnstore_policy('metric.cpu',     after => INTERVAL '7 days');
SELECT add_columnstore_policy('metric.ram',     after => INTERVAL '7 days');
SELECT add_columnstore_policy('metric.disk',    after => INTERVAL '7 days');
SELECT add_columnstore_policy('metric.table',   after => INTERVAL '7 days');
SELECT add_columnstore_policy('metric.index',   after => INTERVAL '7 days');
SELECT add_columnstore_policy('metric.column',  after => INTERVAL '7 days');


-- retention ------------------------------------------------------------------
-- nobody wants 3-second lock samples from a year ago. 90 days is enough for
-- a full quarter of incident review. metadata metrics are cheap so we keep
-- those for a year for trend analysis.

SELECT add_retention_policy('metric.session', INTERVAL '90 days');
SELECT add_retention_policy('metric.lock',    INTERVAL '90 days');
SELECT add_retention_policy('metric.io',      INTERVAL '90 days');
SELECT add_retention_policy('metric.cpu',     INTERVAL '90 days');
SELECT add_retention_policy('metric.ram',     INTERVAL '90 days');
SELECT add_retention_policy('metric.disk',    INTERVAL '1 year');
SELECT add_retention_policy('metric.table',   INTERVAL '1 year');
SELECT add_retention_policy('metric.index',   INTERVAL '1 year');
SELECT add_retention_policy('metric.column',  INTERVAL '1 year');


-- chunk skipping -------------------------------------------------------------
-- timescale already excludes chunks by time automatically. this is the opt-in
-- version for non-time columns: track min/max per chunk so a query like
-- "where database_id = 5" can skip whole chunks whose range doesn't include 5
-- before any decompression. only really pays off when values cluster by time
-- (e.g. databases added later only appear in newer chunks), but it's free
-- when it doesn't help.

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
