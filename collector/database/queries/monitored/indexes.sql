SELECT
    c.oid AS table_oid,
    n.nspname AS schema_name,
    c.relname AS table_name,
    ic.oid AS index_oid,
    ic.relname AS index_name,
    am.amname AS index_type,
    pg_get_indexdef(ic.oid) AS definition,
    i.indisunique AS is_unique,
    i.indisprimary AS is_primary,
    array_agg(
        json_build_object(
            'column_attnum', a.attnum,
            'ordinal', array_position(i.indkey, a.attnum)
        ) ORDER BY array_position(i.indkey, a.attnum)
    ) AS columns_info
FROM pg_index i
JOIN pg_class ic ON ic.oid = i.indexrelid
JOIN pg_class c ON c.oid = i.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_am am ON am.oid = ic.relam
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
GROUP BY c.oid, n.nspname, c.relname, ic.oid, ic.relname, am.amname, i.indisunique, i.indisprimary;