"""Typed union of pg_stat_statements fields across supported PostgreSQL versions."""

COUNTERS = (
    "plans", "rows", "shared_blks_dirtied", "shared_blks_written",
    "local_blks_hit", "local_blks_read", "local_blks_dirtied", "local_blks_written",
    "temp_blks_read", "temp_blks_written", "wal_records", "wal_fpi",
    "wal_buffers_full", "jit_functions", "jit_inlining_count",
    "jit_optimization_count", "jit_emission_count", "jit_deform_count",
    "parallel_workers_to_launch", "parallel_workers_launched",
)
TIMINGS = (
    "total_plan_time", "min_plan_time", "max_plan_time", "mean_plan_time",
    "stddev_plan_time", "min_exec_time", "max_exec_time", "mean_exec_time",
    "stddev_exec_time", "blk_read_time", "blk_write_time", "shared_blk_read_time",
    "shared_blk_write_time", "local_blk_read_time", "local_blk_write_time",
    "temp_blk_read_time", "temp_blk_write_time", "jit_generation_time",
    "jit_inlining_time", "jit_optimization_time", "jit_emission_time", "jit_deform_time",
)
TIMESTAMPS = ("stats_since", "minmax_stats_since")
EXTRA_FIELDS = COUNTERS + TIMINGS + TIMESTAMPS + ("wal_bytes", "source_database_oid")
