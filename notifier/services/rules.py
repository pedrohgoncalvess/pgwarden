from dataclasses import dataclass
from typing import Any, Callable, Mapping


RowMapper = Callable[[Mapping[str, Any]], tuple[str, float] | None]


@dataclass(frozen=True)
class RuleType:
    type: str
    scope: str
    message: str
    query: str
    mapper: RowMapper
    default_warning: float
    default_critical: float
    default_direction: str = "above"


def _simple(entity_column: str, value_column: str) -> RowMapper:
    def mapper(row: Mapping[str, Any]) -> tuple[str, float] | None:
        value = row.get(value_column)
        if value is None:
            return None
        return str(row.get(entity_column, "?")), float(value)

    return mapper


def _dead_tuple_ratio(row: Mapping[str, Any]) -> tuple[str, float] | None:
    dead = row.get("n_dead_tup") or 0
    live = row.get("n_live_tup") or 0
    total = live + dead
    if total <= 0:
        return None
    return str(row.get("entity", "?")), float(dead) / float(total)


def _latest_per_server(table: str, value_column: str) -> str:
    return f"""
        SELECT DISTINCT ON (m.server_id) s.name AS entity, m.{value_column} AS value
        FROM metric.{table} m
        JOIN collector.server s ON s.id = m.server_id
        WHERE m.collected_at > now() - make_interval(mins => :window)
          AND (:entity_id IS NULL OR m.server_id = :entity_id)
        ORDER BY m.server_id, m.collected_at DESC
    """


def _delta_per_database(value_column: str) -> str:
    return f"""
        SELECT d.db_name AS entity,
               (MAX(ds.{value_column}) - MIN(ds.{value_column}))::float AS value
        FROM metric.database_stat ds
        JOIN metadata.database d ON d.id = ds.database_id
        WHERE ds.collected_at > now() - make_interval(mins => :window)
          AND (:entity_id IS NULL OR ds.database_id = :entity_id)
        GROUP BY d.db_name
    """


def _metadata_count_per_database(table: str, timestamp_column: str) -> str:
    return f"""
        SELECT d.db_name AS entity, COUNT(*)::float AS value
        FROM metadata.{table} m
        JOIN metadata.database d ON d.id = m.database_id
        WHERE m.{timestamp_column} > now() - make_interval(mins => :window)
          AND (:entity_id IS NULL OR m.database_id = :entity_id)
        GROUP BY d.db_name
    """


RULE_TYPES: dict[tuple[str, str], RuleType] = {
    ("server", "cpu_percent"): RuleType(
        type="cpu_percent",
        scope="server",
        message="Uso de CPU acima do threshold",
        query=_latest_per_server("cpu", "cpu_percent"),
        mapper=_simple("entity", "value"),
        default_warning=85.0,
        default_critical=95.0,
    ),
    ("server", "ram_percent"): RuleType(
        type="ram_percent",
        scope="server",
        message="Uso de memória acima do threshold",
        query=_latest_per_server("ram", "percent"),
        mapper=_simple("entity", "value"),
        default_warning=90.0,
        default_critical=95.0,
    ),
    ("server", "disk_percent"): RuleType(
        type="disk_percent",
        scope="server",
        message="Uso de disco acima do threshold",
        query="""
            SELECT DISTINCT ON (dk.server_id, dk.mount_point)
                   s.name || ' ' || dk.mount_point AS entity, dk.percent AS value
            FROM metric.disk dk
            JOIN collector.server s ON s.id = dk.server_id
            WHERE dk.collected_at > now() - make_interval(mins => :window)
              AND (:entity_id IS NULL OR dk.server_id = :entity_id)
            ORDER BY dk.server_id, dk.mount_point, dk.collected_at DESC
        """,
        mapper=_simple("entity", "value"),
        default_warning=90.0,
        default_critical=97.0,
    ),
    ("database", "growth_percent"): RuleType(
        type="growth_percent",
        scope="database",
        message="Banco cresceu acima do threshold na janela",
        query="""
            SELECT d.db_name AS entity,
                   (MAX(ds.db_size_bytes) - MIN(ds.db_size_bytes))::float
                     / NULLIF(MIN(ds.db_size_bytes), 0) * 100 AS value
            FROM metric.database_stat ds
            JOIN metadata.database d ON d.id = ds.database_id
            WHERE ds.collected_at > now() - make_interval(mins => :window)
              AND (:entity_id IS NULL OR ds.database_id = :entity_id)
            GROUP BY d.db_name
        """,
        mapper=_simple("entity", "value"),
        default_warning=10.0,
        default_critical=25.0,
    ),
    ("database", "cache_hit_ratio"): RuleType(
        type="cache_hit_ratio",
        scope="database",
        message="Cache hit ratio abaixo do threshold",
        query="""
            SELECT d.db_name AS entity,
                   (MAX(ds.blks_hit) - MIN(ds.blks_hit))::float
                     / NULLIF((MAX(ds.blks_hit) - MIN(ds.blks_hit))
                            + (MAX(ds.blks_read) - MIN(ds.blks_read)), 0) AS value
            FROM metric.database_stat ds
            JOIN metadata.database d ON d.id = ds.database_id
            WHERE ds.collected_at > now() - make_interval(mins => :window)
              AND (:entity_id IS NULL OR ds.database_id = :entity_id)
            GROUP BY d.db_name
        """,
        mapper=_simple("entity", "value"),
        default_warning=0.95,
        default_critical=0.90,
        default_direction="below",
    ),
    ("database", "deadlocks"): RuleType(
        type="deadlocks",
        scope="database",
        message="Deadlocks detectados na janela",
        query=_delta_per_database("deadlocks"),
        mapper=_simple("entity", "value"),
        default_warning=1.0,
        default_critical=5.0,
    ),
    ("database", "tup_updated"): RuleType(
        type="tup_updated",
        scope="database",
        message="Volume de updates acima do threshold na janela",
        query=_delta_per_database("tup_updated"),
        mapper=_simple("entity", "value"),
        default_warning=100000.0,
        default_critical=1000000.0,
    ),
    ("database", "tup_deleted"): RuleType(
        type="tup_deleted",
        scope="database",
        message="Volume de deletes acima do threshold na janela",
        query=_delta_per_database("tup_deleted"),
        mapper=_simple("entity", "value"),
        default_warning=100000.0,
        default_critical=1000000.0,
    ),
    ("database", "long_query_ms"): RuleType(
        type="long_query_ms",
        scope="database",
        message="Query ativa há mais tempo que o threshold",
        query="""
            SELECT d.db_name || ' pid ' || nq.pid AS entity,
                   MAX(nq.query_duration_ms) AS value
            FROM metric.native_query nq
            JOIN metadata.database d ON d.id = nq.database_id
            WHERE nq.collected_at > now() - make_interval(mins => :window)
              AND nq.state = 'active'
              AND (:entity_id IS NULL OR nq.database_id = :entity_id)
            GROUP BY d.db_name, nq.pid, nq.backend_start
        """,
        mapper=_simple("entity", "value"),
        default_warning=30000.0,
        default_critical=120000.0,
    ),
    ("database", "waiting_sessions"): RuleType(
        type="waiting_sessions",
        scope="database",
        message="Sessões aguardando em wait events",
        query="""
            SELECT d.db_name AS entity, COUNT(*)::float AS value
            FROM metric.session sn
            JOIN metadata.database d ON d.id = sn.database_id
            WHERE sn.collected_at = (
                      SELECT MAX(collected_at) FROM metric.session
                      WHERE collected_at > now() - make_interval(mins => :window)
                  )
              AND sn.wait_event_type IS NOT NULL
              AND (:entity_id IS NULL OR sn.database_id = :entity_id)
            GROUP BY d.db_name
        """,
        mapper=_simple("entity", "value"),
        default_warning=5.0,
        default_critical=20.0,
    ),
    ("database", "blocked_locks"): RuleType(
        type="blocked_locks",
        scope="database",
        message="Locks aguardando concessão (bloqueados)",
        query="""
            SELECT d.db_name AS entity, COUNT(*)::float AS value
            FROM metric.lock lk
            JOIN metadata.database d ON d.id = lk.database_id
            WHERE lk.collected_at = (
                      SELECT MAX(collected_at) FROM metric.lock
                      WHERE collected_at > now() - make_interval(mins => :window)
                  )
              AND lk.is_granted = false
              AND (:entity_id IS NULL OR lk.database_id = :entity_id)
            GROUP BY d.db_name
        """,
        mapper=_simple("entity", "value"),
        default_warning=1.0,
        default_critical=5.0,
    ),
    ("database", "table_created"): RuleType(
        type="table_created",
        scope="database",
        message="Tabelas criadas na janela",
        query=_metadata_count_per_database("table", "created_at"),
        mapper=_simple("entity", "value"),
        default_warning=1.0,
        default_critical=10.0,
    ),
    ("database", "table_dropped"): RuleType(
        type="table_dropped",
        scope="database",
        message="Tabelas removidas na janela",
        query=_metadata_count_per_database("table", "deleted_at"),
        mapper=_simple("entity", "value"),
        default_warning=1.0,
        default_critical=5.0,
    ),
    ("database", "index_created"): RuleType(
        type="index_created",
        scope="database",
        message="Índices criados na janela",
        query=_metadata_count_per_database("index", "created_at"),
        mapper=_simple("entity", "value"),
        default_warning=1.0,
        default_critical=10.0,
    ),
    ("database", "index_dropped"): RuleType(
        type="index_dropped",
        scope="database",
        message="Índices removidos na janela",
        query=_metadata_count_per_database("index", "deleted_at"),
        mapper=_simple("entity", "value"),
        default_warning=1.0,
        default_critical=5.0,
    ),
    ("table", "growth_percent"): RuleType(
        type="growth_percent",
        scope="table",
        message="Tabela cresceu acima do threshold na janela",
        query="""
            WITH bounds AS (
                SELECT table_id,
                       MIN(table_size_bytes) AS min_size,
                       MAX(table_size_bytes) AS max_size
                FROM metric.table
                WHERE collected_at > now() - make_interval(mins => :window)
                  AND (:entity_id IS NULL OR table_id = :entity_id)
                GROUP BY table_id
            )
            SELECT mt.schema_name || '.' || mt.name AS entity,
                   (b.max_size - b.min_size)::float / NULLIF(b.min_size, 0) * 100 AS value
            FROM bounds b
            JOIN metadata.table mt ON mt.id = b.table_id
        """,
        mapper=_simple("entity", "value"),
        default_warning=20.0,
        default_critical=50.0,
    ),
    ("table", "dead_tuples"): RuleType(
        type="dead_tuples",
        scope="table",
        message="Tabela com muitas dead tuples (vacuum necessário)",
        query="""
            SELECT DISTINCT ON (t.table_id)
                   mt.schema_name || '.' || mt.name AS entity,
                   t.n_dead_tup::float AS value
            FROM metric.table t
            JOIN metadata.table mt ON mt.id = t.table_id
            WHERE t.collected_at > now() - make_interval(mins => :window)
              AND (:entity_id IS NULL OR t.table_id = :entity_id)
            ORDER BY t.table_id, t.collected_at DESC
        """,
        mapper=_simple("entity", "value"),
        default_warning=10000.0,
        default_critical=100000.0,
    ),
    ("table", "dead_tuple_ratio"): RuleType(
        type="dead_tuple_ratio",
        scope="table",
        message="Tabela com ratio de dead tuples alto (vacuum necessário)",
        query="""
            SELECT DISTINCT ON (t.table_id)
                   mt.schema_name || '.' || mt.name AS entity,
                   t.n_dead_tup, t.n_live_tup
            FROM metric.table t
            JOIN metadata.table mt ON mt.id = t.table_id
            WHERE t.collected_at > now() - make_interval(mins => :window)
              AND (:entity_id IS NULL OR t.table_id = :entity_id)
            ORDER BY t.table_id, t.collected_at DESC
        """,
        mapper=_dead_tuple_ratio,
        default_warning=0.2,
        default_critical=0.5,
    ),
    ("table", "column_added"): RuleType(
        type="column_added",
        scope="table",
        message="Colunas adicionadas na janela",
        query="""
            SELECT mt.schema_name || '.' || mt.name AS entity, COUNT(*)::float AS value
            FROM metadata.column c
            JOIN metadata.table mt ON mt.id = c.table_id
            WHERE c.created_at > now() - make_interval(mins => :window)
              AND (:entity_id IS NULL OR c.table_id = :entity_id)
            GROUP BY mt.schema_name, mt.name
        """,
        mapper=_simple("entity", "value"),
        default_warning=1.0,
        default_critical=5.0,
    ),
    ("index", "hit_rate"): RuleType(
        type="hit_rate",
        scope="index",
        message="Hit rate do índice abaixo do threshold",
        query="""
            SELECT mi.name AS entity,
                   (MAX(i.blks_hit) - MIN(i.blks_hit))::float
                     / NULLIF((MAX(i.blks_hit) - MIN(i.blks_hit))
                            + (MAX(i.blks_read) - MIN(i.blks_read)), 0) AS value
            FROM metric.index i
            JOIN metadata.index mi ON mi.id = i.index_id
            WHERE i.collected_at > now() - make_interval(mins => :window)
              AND (:entity_id IS NULL OR i.index_id = :entity_id)
            GROUP BY mi.name
        """,
        mapper=_simple("entity", "value"),
        default_warning=0.90,
        default_critical=0.80,
        default_direction="below",
    ),
}

TODO_TYPES: dict[tuple[str, str], str] = {
    ("table", "update_delete_queries"): "Depende do analytics (parse de queries UPDATE/DELETE por tabela)",
    ("table", "bloating"): "Depende de estimativa de bloat por tabela",
}
