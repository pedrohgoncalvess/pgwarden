SELECT
    pid,
    backend_start,
    usename user_name,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    query_start,
    state_change,
    LEFT(query, 500) AS query_preview
FROM pg_stat_activity
WHERE datid = %(database_oid)s
  AND pid <> pg_backend_pid()
