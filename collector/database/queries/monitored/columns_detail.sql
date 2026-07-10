SELECT
  c.oid AS table_oid,
  a.attnum AS column_attnum,
  s.avg_width,
  s.null_frac AS null_fraction,
  s.n_distinct,
  (COALESCE(s.avg_width, 0) * COALESCE(c.reltuples, 0))::bigint AS estimated_size
FROM pg_catalog.pg_stats s
JOIN pg_catalog.pg_class c ON c.relname = s.tablename
JOIN pg_catalog.pg_namespace n ON n.nspname = s.schemaname AND n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attname = s.attname
WHERE s.schemaname NOT IN ('pg_catalog', 'information_schema')
  AND c.oid = ANY(%(table_oids)s)
