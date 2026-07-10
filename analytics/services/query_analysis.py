from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.database.models.analytics import (
    Query,
    QueryAnalysis,
    QueryAnalysisFinding,
    QueryColumnHit,
    QueryTableHit,
)
from analytics.database.models.metadata import ColumnModel, Database, Index, IndexColumn, Table
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

ANALYSIS_LIMIT = 100
WINDOW_PADDING_SECONDS = 30
BASELINE_SECONDS = 60 * 60


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
class TableInsight:
    table: Table
    metric: TableMetric | None
    condition_columns: list[ColumnModel]
    index_columns: dict[int, list[str]]
    index_names: dict[int, str]
    column_metrics: dict[int, ColumnMetric]


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
        index_columns, index_names = await _index_columns(session, table.id)
        column_metrics = await _latest_column_metrics(session, [column.id for column in condition_columns], ended_at)

        insights.append(
            TableInsight(
                table=table,
                metric=table_metric,
                condition_columns=condition_columns,
                index_columns=index_columns,
                index_names=index_names,
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


async def _index_columns(session: AsyncSession, table_id: int) -> tuple[dict[int, list[str]], dict[int, str]]:
    result = await session.execute(
        select(Index.id, Index.name, ColumnModel.name)
        .join(IndexColumn, IndexColumn.index_id == Index.id)
        .join(ColumnModel, ColumnModel.id == IndexColumn.column_id)
        .where(Index.table_id == table_id)
        .where(Index.deleted_at.is_(None))
        .order_by(Index.id.asc(), IndexColumn.ordinal_position.asc())
    )
    columns: dict[int, list[str]] = {}
    names: dict[int, str] = {}
    for index_id, index_name, column_name in result.all():
        columns.setdefault(index_id, []).append(column_name)
        names[index_id] = index_name
    return columns, names


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


def _analyze_context(context: QueryContext) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    findings.extend(_resource_findings(context))
    findings.extend(_lock_findings(context))
    findings.extend(_missing_index_findings(context))
    findings.extend(_maintenance_findings(context))
    return sorted(findings, key=lambda finding: finding.confidence, reverse=True)


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
                title="CPU alta durante a query",
                explanation="O servidor apresentou uso elevado de CPU na janela temporal da query.",
                recommendation="Verifique concorrencia no servidor e avalie reduzir custo da query antes de atribuir o problema ao banco isoladamente.",
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
                title="Memoria pressionada durante a query",
                explanation="O uso de memoria estava alto na janela da query, o que pode reduzir cache efetivo e aumentar leituras em disco.",
                recommendation="Verifique consumo de memoria do host e correlacione com leituras de disco antes de ajustar parametros do PostgreSQL.",
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
                    title="I/O elevado correlacionado com a query",
                    explanation="A janela da query coincide com alta taxa de leitura/escrita ou espera de I/O na sessao.",
                    recommendation="Verifique se a query esta fazendo scans grandes, se ha cache suficiente e se o storage esta saturado.",
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
                title="Disco com pouco espaco livre",
                explanation="O volume monitorado estava com uso alto durante a query.",
                recommendation="Libere espaco ou expanda o volume; pouco espaco pode afetar operacoes temporarias, WAL e manutencao.",
                evidence={
                    "disk_max_percent": round(max(disk_values), 2),
                    "disk_avg_percent": round(mean(disk_values), 2),
                },
            )
        )

    return findings


def _lock_findings(context: QueryContext) -> list[FindingDraft]:
    lock_waits = [sample for sample in context.session_samples if sample.wait_event_type == "Lock"]
    ungranted_locks = [lock for lock in context.lock_samples if lock.is_granted is False]
    if not lock_waits and not ungranted_locks:
        return []

    return [
        FindingDraft(
            type="lock_contention",
            severity="critical" if lock_waits else "warning",
            confidence=0.9 if lock_waits else 0.72,
            title="Possivel contencao de locks",
            explanation="A sessao da query ou as tabelas acessadas apresentaram espera/locks na mesma janela temporal.",
            recommendation="Identifique sessoes bloqueadoras e revise transacoes longas ou operacoes concorrentes nas tabelas afetadas.",
            evidence={
                "session_lock_wait_samples": len(lock_waits),
                "ungranted_lock_samples": len(ungranted_locks),
                "lock_modes": sorted({lock.mode for lock in context.lock_samples if lock.mode}),
                "wait_events": sorted({sample.wait_event for sample in lock_waits if sample.wait_event}),
            },
        )
    ]


def _missing_index_findings(context: QueryContext) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for insight in context.tables:
        if not insight.condition_columns:
            continue

        indexed_prefixes = {
            columns[0]
            for columns in insight.index_columns.values()
            if columns
        }
        missing_columns = [column for column in insight.condition_columns if column.name not in indexed_prefixes]
        if not missing_columns:
            continue

        metric = insight.metric
        large_table = bool(metric and (metric.n_live_tup or 0) >= 10_000)
        seq_scan_heavy = bool(metric and (metric.seq_scan or 0) > max(metric.idx_scan or 0, 1) * 3)
        confidence = 0.55
        if large_table:
            confidence += 0.15
        if seq_scan_heavy:
            confidence += 0.15

        findings.append(
            FindingDraft(
                type="missing_index",
                severity="warning",
                confidence=min(confidence, 0.9),
                title=f"Possivel indice ausente em {insight.table.schema_name}.{insight.table.name}",
                explanation="A query usa colunas em condicoes, mas nao ha indice conhecido cujo prefixo comece por essas colunas.",
                recommendation="Avalie criar um indice alinhado aos predicados mais seletivos da query; valide com EXPLAIN antes de aplicar em producao.",
                evidence={
                    "table": f"{insight.table.schema_name}.{insight.table.name}",
                    "missing_prefix_columns": [column.name for column in missing_columns],
                    "existing_index_prefixes": sorted(indexed_prefixes),
                    "n_live_tup": metric.n_live_tup if metric else None,
                    "seq_scan": metric.seq_scan if metric else None,
                    "idx_scan": metric.idx_scan if metric else None,
                    "condition_column_stats": {
                        column.name: _column_metric_evidence(insight.column_metrics.get(column.id))
                        for column in missing_columns
                    },
                },
            )
        )

    return findings


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
                    title=f"Dead tuples altos em {insight.table.schema_name}.{insight.table.name}",
                    explanation="A tabela acessada pela query tem volume relevante de dead tuples, o que pode aumentar custo de scans.",
                    recommendation="Verifique autovacuum e considere VACUUM (ANALYZE) fora do horario critico se a situacao persistir.",
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
                    title=f"Estatisticas possivelmente desatualizadas em {insight.table.schema_name}.{insight.table.name}",
                    explanation="A tabela acessada pela query tem muitas modificacoes desde o ultimo analyze ou estatisticas antigas.",
                    recommendation="Execute ANALYZE na tabela ou ajuste autovacuum/analyze se o padrao se repetir.",
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


def _summary(findings: list[FindingDraft]) -> str:
    if not findings:
        return "Nenhum culpado provavel identificado com as metricas disponiveis."

    top = findings[0]
    if len(findings) == 1:
        return f"Hipotese principal: {top.title}."

    return f"Hipotese principal: {top.title}. Outros sinais encontrados: {len(findings) - 1}."
