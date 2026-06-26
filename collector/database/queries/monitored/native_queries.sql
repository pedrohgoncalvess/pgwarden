SELECT
    pid,
    leader_pid,
    usesysid,
    usename AS user_name,
    application_name,
    client_addr,
    client_hostname,
    client_port,
    backend_start,
    xact_start,
    query_start,
    state_change,
    wait_event_type,
    wait_event,
    state,
    backend_xid::text AS backend_xid,
    backend_xmin::text AS backend_xmin,
    query_id,
    backend_type,
    query,
    md5(query) AS query_hash,
    CASE
        WHEN query_start IS NULL THEN NULL
        ELSE EXTRACT(EPOCH FROM (clock_timestamp() - query_start)) * 1000
    END AS query_duration_ms,
    CASE
        WHEN xact_start IS NULL THEN NULL
        ELSE EXTRACT(EPOCH FROM (clock_timestamp() - xact_start)) * 1000
    END AS transaction_duration_ms,
    CASE
        WHEN backend_start IS NULL THEN NULL
        ELSE EXTRACT(EPOCH FROM (clock_timestamp() - backend_start)) * 1000
    END AS backend_duration_ms
FROM pg_stat_activity
WHERE datid = %(database_oid)s
  AND pid <> pg_backend_pid()
