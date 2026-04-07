SELECT
  c.oid AS table_oid,
  n.nspname AS schema_name,
  c.relname AS table_name,
  a.attname AS name,
  pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
  NOT a.attnotnull AS is_nullable,
  pg_catalog.pg_get_expr(d.adbin, d.adrelid) AS default_value,
  a.attnum AS ordinal_position,
  fk_refs.foreign_table_oid,
  d_col.description,
  EXISTS (
    SELECT 1
    FROM pg_catalog.pg_index ix
    JOIN pg_catalog.pg_attribute ia
      ON ia.attrelid = ix.indrelid
      AND ia.attnum = ANY(ix.indkey)
    WHERE ix.indrelid = a.attrelid
      AND ia.attnum = a.attnum
      AND ix.indisunique = TRUE
      AND array_length(ix.indkey, 1) = 1
  ) AS is_unique
FROM pg_catalog.pg_attribute a
JOIN pg_catalog.pg_class c
  ON c.oid = a.attrelid
JOIN pg_catalog.pg_namespace n
  ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_attrdef d
  ON d.adrelid = a.attrelid
  AND d.adnum = a.attnum
LEFT JOIN pg_catalog.pg_description d_col
  ON d_col.objoid = a.attrelid
  AND d_col.objsubid = a.attnum
LEFT JOIN LATERAL (
  SELECT confrelid AS foreign_table_oid
  FROM pg_catalog.pg_constraint ct
  WHERE ct.contype = 'f'
    AND ct.conrelid = a.attrelid
    AND ct.conkey[1] = a.attnum
  LIMIT 1
) fk_refs ON TRUE
WHERE c.relkind = 'r'
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
  AND n.nspname NOT LIKE 'pg_temp_%'
ORDER BY n.nspname, c.relname, a.attnum;
