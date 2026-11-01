from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean, median
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import exists

from analytics.database.models.analytics import (
    Query,
    QueryAnalysis,
    QueryAnalysisFinding,
    QueryColumnHit,
    QueryTableHit,
)
from analytics.database.models.metadata import ColumnModel, Database, Index, IndexColumn, IndexHistory, Table
from analytics.database.models.metric import (
    ColumnMetric,
    CpuMetric,
    DiskMetric,
    IoMetric,
    LockMetric,
    NativeQueryMetric,
    RamMetric,
    SessionMetric,
    TableMetric,
)

from analytics.services.index_advisor import IndexShape, coverage, index_shape, predicate_roles, quote

ANALYSIS_LIMIT = 100
WINDOW_PADDING_SECONDS = 30
BASELINE_SECONDS = 60 * 60
REGRESSION_HISTORY_DAYS = 7
REGRESSION_HISTORY_MIN_SAMPLES = 5
SCHEMA_CHANGE_LOOKBACK_HOURS = 48
REGRESSION_FACTOR_THRESHOLD = 3.0


@dataclass(frozen=True)
class TimeWindow:
    started_at: datetime
    ended_at: datetime


@dataclass(frozen=True)
class FindingDraft:
    type: str
    severity: str
    confidence: float
    title: str
    explanation: str
    recommendation: str | None
    evidence: dict[str, Any]


@dataclass(frozen=True)
class DroppedIndexInfo:
    name: str
    definition: str
    table_id: int
    changed_at: datetime


@dataclass(frozen=True)
class TableInsight:
    table: Table
    metric: TableMetric | None
    condition_columns: list[ColumnModel]
    index_columns: dict[int, list[str]]
    index_names: dict[int, str]
    column_metrics: dict[int, ColumnMetric]
    index_shapes: list[IndexShape] = field(default_factory=list)


@dataclass(frozen=True)
class QueryContext:
    query: Query
    native_query: NativeQueryMetric
    database: Database
    window: TimeWindow
    tables: list[TableInsight]
    cpu_samples: list[CpuMetric]
    cpu_baseline: list[CpuMetric]
    ram_samples: list[RamMetric]
    io_samples: list[IoMetric]
    io_baseline: list[IoMetric]
    disk_samples: list[DiskMetric]
    session_samples: list[SessionMetric]
    lock_samples: list[LockMetric]
    duration_history_ms: list[float]
    recent_dropped_indexes: list[DroppedIndexInfo]


async def process_query_analysis_with_session(
    session: AsyncSession,
    run_id: int,
    database_id: int,
    include_recommendations: bool = True,
    limit: int = ANALYSIS_LIMIT,
) -> int:
    queries = await _pending_queries(session, database_id, limit)
    analyzed = 0

    for query in queries:
        context = await _build_context(session, query)
        if context is None:
            continue

        findings = _analyze_context(context)
        summary = _summary(findings)
        overall_score = max((finding.confidence for finding in findings), default=0.0)

        analysis = QueryAnalysis(
            run_id=run_id,
            query_id=query.id,
            database_id=database_id,
            started_at=context.window.started_at,
            ended_at=context.window.ended_at,
            duration_ms=context.native_query.query_duration_ms,
            overall_score=round(overall_score, 2),
            summary=summary,
        )
        session.add(analysis)
        await session.flush()

        for finding in findings:
            recommendation = finding.recommendation if include_recommendations else None
            session.add(
                QueryAnalysisFinding(
                    analysis_id=analysis.id,
                    type=finding.type,
                    severity=finding.severity,
                    confidence=round(finding.confidence, 2),
                    title=finding.title,
                    explanation=finding.explanation,
                    recommendation=recommendation,
                    evidence=finding.evidence,
                )
            )

        analyzed += 1

    return analyzed


async def _pending_queries(session: AsyncSession, database_id: int, limit: int) -> list[Query]:
    has_analysis = exists().where(QueryAnalysis.query_id == Query.id)
    has_table_hit = exists().where(QueryTableHit.query_id == Query.id)
    result = await session.execute(
        select(Query)
        .where(Query.database_id == database_id)
        .where(~has_analysis)
        .where(has_table_hit)
        .order_by(Query.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _build_context(session: AsyncSession, query: Query) -> QueryContext | None:
    database = await session.get(Database, query.database_id)
    if database is None:
        return None

    native_query = await _latest_native_query(session, query)
    if native_query is None:
        return None

    window = _time_window(native_query)
    baseline_start = window.started_at - timedelta(seconds=BASELINE_SECONDS)
    tables = await _table_insights(session, query.id, query.database_id, window.ended_at)
    table_ids = [table.table.id for table in tables]

    cpu_samples = await _rows_between(session, CpuMetric, database.server_id, window.started_at, window.ended_at)
    cpu_baseline = await _rows_between(session, CpuMetric, database.server_id, baseline_start, window.started_at)
    ram_samples = await _rows_between(session, RamMetric, database.server_id, window.started_at, window.ended_at)
    io_samples = await _rows_between(session, IoMetric, database.server_id, window.started_at, window.ended_at)
    io_baseline = await _rows_between(session, IoMetric, database.server_id, baseline_start, window.started_at)
    disk_samples = await _rows_between(session, DiskMetric, database.server_id, window.started_at, window.ended_at)
    session_samples = await _session_samples(session, native_query, window)
    lock_samples = await _lock_samples(session, query.database_id, table_ids, window)
    duration_history = await _query_duration_history(session, query, days=REGRESSION_HISTORY_DAYS)
    recent_dropped_indexes = await _recent_dropped_indexes(session, query.database_id, window.started_at)

    return QueryContext(
        query=query,
        native_query=native_query,
        database=database,
        window=window,
        tables=tables,
        cpu_samples=cpu_samples,
        cpu_baseline=cpu_baseline,
        ram_samples=ram_samples,
        io_samples=io_samples,
        io_baseline=io_baseline,
        disk_samples=disk_samples,
        session_samples=session_samples,
        lock_samples=lock_samples,
        duration_history_ms=duration_history,
        recent_dropped_indexes=recent_dropped_indexes,
    )


async def _latest_native_query(session: AsyncSession, query: Query) -> NativeQueryMetric | None:
    filters = [NativeQueryMetric.database_id == query.database_id]
    if query.hash:
        filters.append(or_(NativeQueryMetric.query_hash == query.hash, NativeQueryMetric.query == query.query))
    else:
        filters.append(NativeQueryMetric.query == query.query)

    result = await session.execute(
        select(NativeQueryMetric)
        .where(*filters)
        .order_by(NativeQueryMetric.collected_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _time_window(native_query: NativeQueryMetric) -> TimeWindow:
    ended_at = native_query.collected_at
    if native_query.query_start is not None:
        started_at = native_query.query_start
    elif native_query.query_duration_ms is not None:
        started_at = ended_at - timedelta(milliseconds=max(native_query.query_duration_ms, 0))
    else:
        started_at = ended_at - timedelta(seconds=WINDOW_PADDING_SECONDS)

    if started_at > ended_at:
        started_at = ended_at

    return TimeWindow(
        started_at=started_at - timedelta(seconds=WINDOW_PADDING_SECONDS),
        ended_at=ended_at + timedelta(seconds=WINDOW_PADDING_SECONDS),
    )


async def _table_insights(
    session: AsyncSession,
    query_id: int,
    database_id: int,
    ended_at: datetime,
) -> list[TableInsight]:
    table_hits_result = await session.execute(select(QueryTableHit).where(QueryTableHit.query_id == query_id))
    table_hits = list(table_hits_result.scalars().all())
    condition_hits_result = await session.execute(
        select(QueryColumnHit)
        .where(QueryColumnHit.query_id == query_id)
        .where(or_(QueryColumnHit.is_condition.is_(True), QueryColumnHit.is_condition_foreign.is_(True)))
    )
    condition_hits = list(condition_hits_result.scalars().all())
    insights: list[TableInsight] = []

    for hit in table_hits:
        table_result = await session.execute(
            select(Table)
            .where(Table.database_id == database_id)
            .where(Table.schema_name == hit.schema_name)
            .where(Table.name == hit.table_name)
            .where(Table.deleted_at.is_(None))
            .limit(1)
        )
        table = table_result.scalar_one_or_none()
        if table is None:
            continue

        table_metric = await _latest_table_metric(session, table.id, ended_at)
        condition_columns = await _condition_columns(session, table, condition_hits)
        index_columns, index_names, index_shapes = await _index_columns(session, table.id)
        column_metrics = await _latest_column_metrics(session, [column.id for column in condition_columns], ended_at)

        insights.append(
            TableInsight(
                table=table,
                metric=table_metric,
                condition_columns=condition_columns,
                index_columns=index_columns,
                index_names=index_names,
                index_shapes=index_shapes,
                column_metrics=column_metrics,
            )
        )

    return insights


async def _latest_table_metric(session: AsyncSession, table_id: int, ended_at: datetime) -> TableMetric | None:
    result = await session.execute(
        select(TableMetric)
        .where(TableMetric.table_id == table_id)
        .where(TableMetric.collected_at <= ended_at)
        .order_by(TableMetric.collected_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _condition_columns(
    session: AsyncSession,
    table: Table,
    condition_hits: list[QueryColumnHit],
) -> list[ColumnModel]:
    names = {
        hit.column_name
        for hit in condition_hits
        if hit.schema_name == table.schema_name and hit.table_name == table.name
    }
    if not names:
        return []

    result = await session.execute(
        select(ColumnModel)
        .where(ColumnModel.table_id == table.id)
        .where(ColumnModel.name.in_(names))
        .where(ColumnModel.deleted_at.is_(None))
    )
    return list(result.scalars().all())


async def _index_columns(session: AsyncSession, table_id: int) -> tuple[dict[int, list[str]], dict[int, str], list[IndexShape]]:
    result = await session.execute(
        select(Index).where(Index.table_id == table_id, Index.deleted_at.is_(None))
    )
    indexes = list(result.scalars().all())
    result = await session.execute(
        select(IndexColumn.index_id, ColumnModel.name)
        .join(ColumnModel, ColumnModel.id == IndexColumn.column_id)
        .join(Index, Index.id == IndexColumn.index_id)
        .where(Index.table_id == table_id, Index.deleted_at.is_(None))
        .order_by(IndexColumn.ordinal_position.asc())
    )
    columns: dict[int, list[str]] = {}
    for index_id, column_name in result.all():
        columns.setdefault(index_id, []).append(column_name)
    shapes = []
    for index in indexes:
        shape = index_shape(index.name, index.definition, index.type)
        if index.is_valid is not True:
            shape = IndexShape(shape.name, shape.keys, False)
        shapes.append(shape)
    return columns, {index.id: index.name for index in indexes}, shapes


async def _latest_column_metrics(
    session: AsyncSession,
    column_ids: list[int],
    ended_at: datetime,
) -> dict[int, ColumnMetric]:
    metrics: dict[int, ColumnMetric] = {}
    for column_id in column_ids:
        result = await session.execute(
            select(ColumnMetric)
            .where(ColumnMetric.column_id == column_id)
            .where(ColumnMetric.collected_at <= ended_at)
            .order_by(ColumnMetric.collected_at.desc())
            .limit(1)
        )
        metric = result.scalar_one_or_none()
        if metric is not None:
            metrics[column_id] = metric
    return metrics


async def _rows_between(session: AsyncSession, model, server_id: int, started_at: datetime, ended_at: datetime) -> list:
    result = await session.execute(
        select(model)
        .where(model.server_id == server_id)
        .where(model.collected_at >= started_at)
        .where(model.collected_at <= ended_at)
        .order_by(model.collected_at.asc())
    )
    return list(result.scalars().all())


async def _session_samples(
    session: AsyncSession,
    native_query: NativeQueryMetric,
    window: TimeWindow,
) -> list[SessionMetric]:
    result = await session.execute(
        select(SessionMetric)
        .where(SessionMetric.database_id == native_query.database_id)
        .where(SessionMetric.collected_at >= window.started_at)
        .where(SessionMetric.collected_at <= window.ended_at)
        .where(SessionMetric.pid == native_query.pid)
        .where(SessionMetric.backend_start == native_query.backend_start)
        .order_by(SessionMetric.collected_at.asc())
    )
    return list(result.scalars().all())


async def _lock_samples(
    session: AsyncSession,
    database_id: int,
    table_ids: list[int],
    window: TimeWindow,
) -> list[LockMetric]:
    statement = (
        select(LockMetric)
        .where(LockMetric.database_id == database_id)
        .where(LockMetric.collected_at >= window.started_at)
        .where(LockMetric.collected_at <= window.ended_at)
    )
    if table_ids:
        statement = statement.where(LockMetric.table_id.in_(table_ids))

    result = await session.execute(statement.order_by(LockMetric.collected_at.asc()))
    return list(result.scalars().all())


async def _query_duration_history(
    session: AsyncSession,
    query: Query,
    days: int = REGRESSION_HISTORY_DAYS,
) -> list[float]:
    """Return recorded duration_ms values for the same query hash over the last N days."""
    if not query.hash:
        return []

    cutoff = datetime.now().astimezone() - timedelta(days=days)
    result = await session.execute(
        select(NativeQueryMetric.query_duration_ms)
        .where(NativeQueryMetric.database_id == query.database_id)
        .where(NativeQueryMetric.query_hash == query.hash)
        .where(NativeQueryMetric.query_duration_ms.is_not(None))
        .where(NativeQueryMetric.collected_at >= cutoff)
        .order_by(NativeQueryMetric.collected_at.asc())
    )
    return [float(row[0]) for row in result.all()]


async def _recent_dropped_indexes(
    session: AsyncSession,
    database_id: int,
    before: datetime,
) -> list[DroppedIndexInfo]:
    """Return indexes that were dropped (deleted_at set) within the lookback window."""
    cutoff = before - timedelta(hours=SCHEMA_CHANGE_LOOKBACK_HOURS)
    result = await session.execute(
        select(Index.id, Index.name, Index.definition, Index.table_id, Index.deleted_at)
        .where(Index.database_id == database_id)
        .where(Index.deleted_at.is_not(None))
        .where(Index.deleted_at >= cutoff)
        .where(Index.deleted_at <= before)
        .order_by(Index.deleted_at.desc())
    )
    return [
        DroppedIndexInfo(
            name=row.name,
            definition=row.definition,
            table_id=row.table_id,
            changed_at=row.deleted_at,
        )
        for row in result.all()
    ]


# ---------------------------------------------------------------------------
# Analysis orchestrator
# ---------------------------------------------------------------------------

def _analyze_context(context: QueryContext) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    findings.extend(_resource_findings(context))
    findings.extend(_lock_findings(context))
    findings.extend(_missing_index_findings(context))
    findings.extend(_maintenance_findings(context))
    findings.extend(_regression_findings(context))
    findings.extend(_schema_change_findings(context))
    return sorted(findings, key=lambda finding: finding.confidence, reverse=True)


# ---------------------------------------------------------------------------
# Resource findings (CPU / RAM / IO / Disk)
# ---------------------------------------------------------------------------

def _resource_findings(context: QueryContext) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    cpu_values = _values(context.cpu_samples, "cpu_percent")
    baseline_cpu = _values(context.cpu_baseline, "cpu_percent")
    ram_values = _values(context.ram_samples, "percent")
    disk_values = _values(context.disk_samples, "percent")
    io_rate = _io_rate(context.io_samples)
    baseline_io_rate = _io_rate(context.io_baseline)
    wait_types = [sample.wait_event_type for sample in context.session_samples if sample.wait_event_type]
    wait_events = [sample.wait_event for sample in context.session_samples if sample.wait_event]

    if cpu_values and max(cpu_values) >= 85:
        baseline_avg = mean(baseline_cpu) if baseline_cpu else None
        confidence = 0.65
        if baseline_avg is not None and mean(cpu_values) > baseline_avg * 1.4:
            confidence += 0.15
        if "CPU" in wait_types:
            confidence += 0.15

        findings.append(
            FindingDraft(
                type="resource_cpu",
                severity="critical" if max(cpu_values) >= 95 else "warning",
                confidence=min(confidence, 0.95),
                title="High CPU during query execution",
                explanation="The server showed elevated CPU usage during this query's execution window.",
                recommendation="Review server concurrency and reduce query cost before attributing the issue to the database alone.",
                evidence={
                    "cpu_avg": round(mean(cpu_values), 2),
                    "cpu_max": round(max(cpu_values), 2),
                    "baseline_cpu_avg": round(baseline_avg, 2) if baseline_avg is not None else None,
                    "sample_count": len(cpu_values),
                    "wait_event_types": sorted(set(wait_types)),
                },
            )
        )

    if ram_values and max(ram_values) >= 90:
        findings.append(
            FindingDraft(
                type="resource_memory",
                severity="warning",
                confidence=0.62,
                title="Memory pressure during query execution",
                explanation="Memory usage was high during this query, which can reduce effective cache and increase disk reads.",
                recommendation="Review host memory consumption and correlate it with disk reads before tuning PostgreSQL settings.",
                evidence={
                    "ram_avg_percent": round(mean(ram_values), 2),
                    "ram_max_percent": round(max(ram_values), 2),
                    "sample_count": len(ram_values),
                },
            )
        )

    if io_rate["bytes_per_second"] > 0:
        baseline_rate = baseline_io_rate["bytes_per_second"]
        io_wait = "IO" in wait_types or any(wait in {"DataFileRead", "DataFileWrite"} for wait in wait_events)
        high_vs_baseline = baseline_rate > 0 and io_rate["bytes_per_second"] > baseline_rate * 3
        if io_wait or high_vs_baseline:
            confidence = 0.65
            if high_vs_baseline:
                confidence += 0.15
            if io_wait:
                confidence += 0.15

            findings.append(
                FindingDraft(
                    type="resource_io",
                    severity="critical" if io_wait and high_vs_baseline else "warning",
                    confidence=min(confidence, 0.95),
                    title="High I/O correlated with query execution",
                    explanation="The query window overlaps high read/write activity or I/O waits in the session.",
                    recommendation="Check for large scans, insufficient cache, and saturated storage.",
                    evidence={
                        "io_bytes_per_second": round(io_rate["bytes_per_second"], 2),
                        "baseline_io_bytes_per_second": round(baseline_rate, 2),
                        "read_bytes_per_second": round(io_rate["read_bytes_per_second"], 2),
                        "write_bytes_per_second": round(io_rate["write_bytes_per_second"], 2),
                        "wait_event_types": sorted(set(wait_types)),
                        "wait_events": sorted(set(wait_events)),
                    },
                )
            )

    if disk_values and max(disk_values) >= 90:
        findings.append(
            FindingDraft(
                type="resource_disk_space",
                severity="critical" if max(disk_values) >= 97 else "warning",
                confidence=0.7,
                title="Low disk headroom",
                explanation="The monitored volume was highly utilized during this query.",
                recommendation="Free space or expand the volume; low headroom can affect temporary operations, WAL, and maintenance.",
                evidence={
                    "disk_max_percent": round(max(disk_values), 2),
                    "disk_avg_percent": round(mean(disk_values), 2),
                },
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Lock findings
# ---------------------------------------------------------------------------

def _lock_findings(context: QueryContext) -> list[FindingDraft]:
    lock_waits = [sample for sample in context.session_samples if sample.wait_event_type == "Lock"]
    ungranted_locks = [lock for lock in context.lock_samples if lock.is_granted is False]
    if not lock_waits and not ungranted_locks:
        return []

    # Build a simple blocking chain from exclusive vs. shared overlap
    exclusive_modes = {"ExclusiveLock", "AccessExclusiveLock", "RowExclusiveLock"}
    exclusive_holders = [
        lock for lock in context.lock_samples
        if lock.is_granted is True and lock.mode in exclusive_modes
    ]
    blocking_chain: list[dict] = []
    for holder in exclusive_holders:
        if holder.query_preview:
            blocking_chain.append({
                "holder_pid": holder.holder_pid,
                "mode": holder.mode,
                "query_preview": holder.query_preview[:200],
            })

    return [
        FindingDraft(
            type="lock_contention",
            severity="critical" if lock_waits else "warning",
            confidence=0.9 if lock_waits else 0.72,
            title="Possible lock contention",
            explanation="The query session or accessed tables showed lock waits during the same time window.",
            recommendation="Identify blocking sessions and review long transactions or concurrent operations on affected tables.",
            evidence={
                "session_lock_wait_samples": len(lock_waits),
                "ungranted_lock_samples": len(ungranted_locks),
                "lock_modes": sorted({lock.mode for lock in context.lock_samples if lock.mode}),
                "wait_events": sorted({sample.wait_event for sample in lock_waits if sample.wait_event}),
                "blocking_chain": blocking_chain,
            },
        )
    ]


# ---------------------------------------------------------------------------
# Missing index findings (with selectivity awareness and DDL suggestion)
# ---------------------------------------------------------------------------

def _estimate_selectivity(metric: ColumnMetric | None, n_live_tup: int | None) -> float | None:
    """
    Return an estimated selectivity fraction (0..1) where lower = more selective
    (i.e. lower fraction of rows share the same value).

    PostgreSQL pg_stats.n_distinct semantics:
      - negative:  fraction of rows that are distinct (e.g. -0.98 ≈ 98% unique).
                   Selectivity ≈ abs(n_distinct) / n_distinct_values = 1 / (abs(n_distinct) * rows)
                   Simplified: abs(n_distinct) already expresses the *fraction of total rows per value*
                   but inverted — more-negative means more selective.
                   We return  1.0 / (abs(n_distinct) * rows) so that higher-cardinality columns get
                   lower selectivity scores.
      - positive:  absolute count of distinct values.  Selectivity per value = 1 / n_distinct
                   normalised by rows so it is comparable with the negative case.
    Returns None when insufficient data is available.
    """
    if metric is None or metric.n_distinct is None:
        return None
    n_distinct = metric.n_distinct
    rows = max(n_live_tup or 1, 1)
    if n_distinct < 0:
        # abs gives the fraction of rows that are distinct values (e.g. 0.98 for near-unique).
        # We want: how many rows share each distinct value on average?
        # avg_rows_per_value = rows * (1 - abs(n_distinct))   ... for duplication
        # selectivity = avg_rows_per_value / rows = (1 - abs(n_distinct))
        # Lower = more selective (less duplication per value).
        return 1.0 - abs(n_distinct)
    if n_distinct == 0:
        return None
    # positive: absolute count of distinct values → fraction of rows sharing each value
    return rows / n_distinct / rows  # simplifies to 1 / n_distinct (fraction per value)


def _suggest_index_ddl(table: Table, columns: list[ColumnModel], column_metrics: dict[int, ColumnMetric], n_live_tup: int | None) -> str:
    """
    Deterministically suggest a CREATE INDEX statement.
    Columns are ordered by ascending selectivity (most selective leading column).
    """
    def sort_key(col: ColumnModel) -> float:
        sel = _estimate_selectivity(column_metrics.get(col.id), n_live_tup)
        return sel if sel is not None else 1.0  # unknown → treat as least selective

    sorted_cols = sorted(columns, key=sort_key)
    col_list = ", ".join(col.name for col in sorted_cols)
    qualified = f"{table.schema_name}.{table.name}"
    return f"CREATE INDEX CONCURRENTLY ON {qualified} ({col_list});"


def _missing_index_findings(context: QueryContext) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for insight in context.tables:
        if not insight.condition_columns:
            continue
        names = {column.name for column in insight.condition_columns}
        equality, ranges, understood = predicate_roles(context.query.query, names)
        shapes = getattr(insight, "index_shapes", [])
        if not shapes and insight.index_columns:
            shapes = [IndexShape(insight.index_names.get(key, str(key)), tuple(cols), False)
                      for key, cols in insight.index_columns.items()]
        state, matching = coverage(shapes, equality, ranges, understood)
        if state == "covered":
            continue
        metric = insight.metric
        # Keep the entire predicate instead of indexing only residual columns.
        columns = sorted(names, key=lambda name: (name not in equality, name))
        ddl = None
        if state == "missing" and len(ranges) <= 1:
            qualified = f"{quote(insight.table.schema_name)}.{quote(insight.table.name)}"
            ddl = f"CREATE INDEX CONCURRENTLY ON {qualified} ({', '.join(quote(c) for c in columns)});"
        confidence = 0.5 if ddl else 0.35
        if metric and (metric.n_live_tup or 0) >= 10_000:
            confidence += 0.1
        table_name = f"{insight.table.schema_name}.{insight.table.name}"
        findings.append(FindingDraft(
            type="missing_index", severity="info", confidence=confidence,
            title=f"Review index coverage on {table_name}",
            explanation=f"Filter index coverage is {state}; execution-plan validation is required.",
            recommendation=(f"Candidate: {ddl} " if ddl else "Review existing indexes and the execution plan. ")
                + "Compare read benefit and write overhead before changing indexes.",
            evidence={
                "table": table_name, "table_id": insight.table.id,
                "missing_prefix_columns": columns, "coverage": state,
                "matching_indexes": matching,
                "existing_index_prefixes": sorted({shape.keys[0] for shape in shapes if shape.keys}),
                "suggested_ddl": ddl, "n_live_tup": metric.n_live_tup if metric else None,
                "equality_columns": sorted(equality), "range_columns": sorted(ranges),
                "requires_plan_validation": True, "advisor_version": 2,
            },
        ))
    return findings


# ---------------------------------------------------------------------------
# Maintenance findings (vacuum / stale stats)
# ---------------------------------------------------------------------------

def _maintenance_findings(context: QueryContext) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for insight in context.tables:
        metric = insight.metric
        if metric is None:
            continue

        live = metric.n_live_tup or 0
        dead = metric.n_dead_tup or 0
        dead_ratio = dead / max(live, 1)
        if dead >= 10_000 and dead_ratio >= 0.2:
            findings.append(
                FindingDraft(
                    type="vacuum_needed",
                    severity="warning",
                    confidence=0.78,
                    title=f"High dead tuples on {insight.table.schema_name}.{insight.table.name}",
                    explanation="The table accessed by this query has enough dead tuples to increase scan cost.",
                    recommendation="Review autovacuum and consider VACUUM (ANALYZE) outside peak traffic if this persists.",
                    evidence={
                        "table": f"{insight.table.schema_name}.{insight.table.name}",
                        "n_live_tup": live,
                        "n_dead_tup": dead,
                        "dead_tuple_ratio": round(dead_ratio, 4),
                        "last_vacuum": _iso(metric.last_vacuum),
                        "last_autovacuum": _iso(metric.last_autovacuum),
                    },
                )
            )

        modifications = metric.modifications_since_last_analyze or 0
        modification_ratio = modifications / max(live, 1)
        analyze_age_days = _age_days(metric.last_analyze or metric.last_autoanalyze, context.window.ended_at)
        stale_by_modifications = modifications >= 10_000 and modification_ratio >= 0.1
        stale_by_age = analyze_age_days is not None and analyze_age_days >= 7 and live >= 10_000
        if stale_by_modifications or stale_by_age:
            findings.append(
                FindingDraft(
                    type="stale_statistics",
                    severity="warning",
                    confidence=0.74 if stale_by_modifications else 0.62,
                    title=f"Potentially stale statistics on {insight.table.schema_name}.{insight.table.name}",
                    explanation="The table has many changes since its last analyze, or its statistics are old.",
                    recommendation="Run ANALYZE on the table or tune autovacuum/analyze if the pattern recurs.",
                    evidence={
                        "table": f"{insight.table.schema_name}.{insight.table.name}",
                        "n_live_tup": live,
                        "modifications_since_last_analyze": modifications,
                        "modification_ratio": round(modification_ratio, 4),
                        "last_analyze": _iso(metric.last_analyze),
                        "last_autoanalyze": _iso(metric.last_autoanalyze),
                        "analyze_age_days": round(analyze_age_days, 2) if analyze_age_days is not None else None,
                    },
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Query regression detection (NEW)
# ---------------------------------------------------------------------------

def _regression_findings(context: QueryContext) -> list[FindingDraft]:
    """Detect when a query is running significantly slower than its historical baseline."""
    history = context.duration_history_ms
    current_ms = context.native_query.query_duration_ms

    if current_ms is None or len(history) < REGRESSION_HISTORY_MIN_SAMPLES:
        return []

    historical_without_current = [d for d in history if d != current_ms]
    if len(historical_without_current) < REGRESSION_HISTORY_MIN_SAMPLES:
        historical_without_current = history

    p50 = median(historical_without_current)
    p95 = _percentile(historical_without_current, 95)

    if p50 <= 0:
        return []

    regression_factor = current_ms / p50
    if regression_factor < REGRESSION_FACTOR_THRESHOLD:
        return []

    # Confidence scales with how extreme the regression is
    confidence = 0.75
    if regression_factor >= 10.0:
        confidence = 0.92
    elif regression_factor >= 5.0:
        confidence = 0.85

    severity = "critical" if regression_factor >= 10.0 else "warning"

    return [
        FindingDraft(
            type="query_regression",
            severity=severity,
            confidence=confidence,
            title="Significant query performance regression detected",
            explanation=(
                f"This query is running {regression_factor:.1f}x slower than its {REGRESSION_HISTORY_DAYS}-day "
                f"median ({current_ms:.0f} ms vs. median {p50:.0f} ms). "
                "This indicates a recent change in execution conditions."
            ),
            recommendation=(
                "Check for table growth, dropped indexes, stale statistics, or increased lock contention "
                "since the last time this query ran at normal speed. "
                "Use EXPLAIN (ANALYZE, BUFFERS) to compare actual vs. estimated row counts."
            ),
            evidence={
                "current_ms": round(current_ms, 2),
                "historical_p50_ms": round(p50, 2),
                "historical_p95_ms": round(p95, 2),
                "regression_factor": round(regression_factor, 2),
                "history_sample_count": len(history),
                "history_days": REGRESSION_HISTORY_DAYS,
            },
        )
    ]


# ---------------------------------------------------------------------------
# Schema change correlation (NEW)
# ---------------------------------------------------------------------------

def _schema_change_findings(context: QueryContext) -> list[FindingDraft]:
    """
    Detect when a recently dropped index covers tables accessed by this query.
    Correlates schema changes with potential performance impact.
    """
    if not context.recent_dropped_indexes:
        return []

    query_table_ids = {insight.table.id for insight in context.tables}
    relevant_drops = [
        drop for drop in context.recent_dropped_indexes
        if drop.table_id in query_table_ids
    ]

    if not relevant_drops:
        return []

    # Higher confidence when this query also has a regression signal
    has_regression = context.native_query.query_duration_ms is not None and (
        len(context.duration_history_ms) >= REGRESSION_HISTORY_MIN_SAMPLES
        and context.native_query.query_duration_ms > median(context.duration_history_ms) * REGRESSION_FACTOR_THRESHOLD
    )
    confidence = 0.88 if has_regression else 0.72

    dropped_names = [d.name for d in relevant_drops]
    hours_ago = min(
        (context.window.started_at - d.changed_at).total_seconds() / 3600
        for d in relevant_drops
    )

    return [
        FindingDraft(
            type="schema_change_correlation",
            severity="critical" if has_regression else "warning",
            confidence=confidence,
            title=f"Index dropped on accessed table within {SCHEMA_CHANGE_LOOKBACK_HOURS}h window",
            explanation=(
                f"The index(es) {dropped_names} were dropped within {hours_ago:.1f} hours before this query's "
                "execution window. Queries accessing those tables may be performing full sequential scans instead."
            ),
            recommendation=(
                "Review whether the dropped index was required by this or similar queries. "
                "Use EXPLAIN to verify the current query plan and recreate the index if needed: "
                + " | ".join(
                    f"CREATE INDEX CONCURRENTLY {d.name} {_extract_on_clause(d.definition)};"
                    for d in relevant_drops
                )
            ),
            evidence={
                "dropped_indexes": [
                    {
                        "name": d.name,
                        "definition": d.definition,
                        "table_id": d.table_id,
                        "dropped_at": _iso(d.changed_at),
                        "hours_before_query": round(
                            (context.window.started_at - d.changed_at).total_seconds() / 3600, 2
                        ),
                    }
                    for d in relevant_drops
                ],
                "correlated_with_regression": has_regression,
            },
        )
    ]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _values(rows: list, attr: str) -> list[float]:
    return [float(value) for row in rows if (value := getattr(row, attr, None)) is not None]


def _io_rate(rows: list[IoMetric]) -> dict[str, float]:
    if len(rows) < 2:
        return {
            "bytes_per_second": 0.0,
            "read_bytes_per_second": 0.0,
            "write_bytes_per_second": 0.0,
        }

    first = rows[0]
    last = rows[-1]
    seconds = max((last.collected_at - first.collected_at).total_seconds(), 1)
    read_delta = max((last.read_bytes or 0) - (first.read_bytes or 0), 0)
    write_delta = max((last.write_bytes or 0) - (first.write_bytes or 0), 0)
    return {
        "bytes_per_second": (read_delta + write_delta) / seconds,
        "read_bytes_per_second": read_delta / seconds,
        "write_bytes_per_second": write_delta / seconds,
    }


def _column_metric_evidence(metric: ColumnMetric | None) -> dict[str, Any] | None:
    if metric is None:
        return None
    return {
        "null_fraction": metric.null_fraction,
        "n_distinct": metric.n_distinct,
        "avg_width": metric.avg_width,
    }


def _age_days(value: datetime | None, reference: datetime) -> float | None:
    if value is None:
        return None
    return max((reference - value).total_seconds(), 0) / 86_400


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _percentile(values: list[float], p: int) -> float:
    """Return the p-th percentile of a sorted list using the nearest-rank method."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    # Nearest-rank: ceil(p/100 * n), 1-indexed → convert to 0-indexed
    import math
    idx = max(0, math.ceil(p / 100 * n) - 1)
    return sorted_vals[idx]


def _extract_on_clause(definition: str) -> str:
    """
    Extract the ON ... (...) part from an index definition string.
    Falls back to the full definition if it cannot be parsed.
    """
    upper = definition.upper()
    on_pos = upper.find(" ON ")
    if on_pos != -1:
        return definition[on_pos:]
    return definition


def _summary(findings: list[FindingDraft]) -> str:
    if not findings:
        return "No significant issues identified with the available metrics."

    top = findings[0]
    critical = [f for f in findings if f.severity == "critical"]
    warnings = [f for f in findings if f.severity == "warning"]

    parts: list[str] = [f"Primary hypothesis: {top.title}."]
    if len(findings) > 1:
        detail_parts: list[str] = []
        if critical:
            detail_parts.append(f"{len(critical)} critical signal(s)")
        if warnings:
            detail_parts.append(f"{len(warnings)} warning(s)")
        parts.append(f"Also found: {', '.join(detail_parts)}.")
    return " ".join(parts)
