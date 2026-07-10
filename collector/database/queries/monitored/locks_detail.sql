SELECT
    l.pid AS holder_pid,
    l.locktype AS type,
    l.mode AS mode,
    l.granted AS is_granted,
    c.oid AS table_oid,
    LEFT(a.query, 500) AS query_preview
FROM pg_locks l
JOIN pg_stat_activity a ON a.pid = l.pid
LEFT JOIN pg_class c ON l.relation = c.oid
WHERE a.datid = %(database_oid)s
  AND l.pid <> pg_backend_pid()
  AND c.relname IS NOT NULL
