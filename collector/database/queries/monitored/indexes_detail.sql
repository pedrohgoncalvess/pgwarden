SELECT
    s.indexrelid AS index_oid,
    pg_relation_size(s.indexrelid) AS index_size,
    s.idx_scan,
    s.idx_tup_read,
    s.idx_tup_fetch,
    COALESCE(io.idx_blks_read, 0) AS blks_read,
    COALESCE(io.idx_blks_hit, 0) AS blks_hit
FROM pg_catalog.pg_stat_user_indexes s
LEFT JOIN pg_catalog.pg_statio_user_indexes io ON s.indexrelid = io.indexrelid
WHERE s.indexrelid = ANY(%(index_oids)s)
