SELECT
    s.relid AS table_oid,
    s.n_live_tup,
    s.n_dead_tup,
    pg_relation_size(s.relid) AS table_size_bytes,
    s.last_vacuum,
    s.last_autovacuum,
    s.last_analyze,
    s.last_autoanalyze,
    s.seq_scan,
    s.idx_scan,
    s.n_mod_since_analyze,
    COALESCE(io.heap_blks_read, 0) AS heap_blks_read,
    COALESCE(io.heap_blks_hit, 0) AS heap_blks_hit
FROM pg_stat_user_tables s
LEFT JOIN pg_statio_user_tables io ON s.relid = io.relid
WHERE s.relid = ANY(%(table_oids)s)