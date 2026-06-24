SELECT
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    conflicts,
    deadlocks,
    pg_database_size(datid) AS db_size_bytes
FROM pg_stat_database
WHERE datid = %(database_oid)s
