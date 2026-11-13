from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class QueryAnalyticsUserBreakdown(BaseModel):
    user_name: Optional[str]
    execution_count: int

    model_config = ConfigDict(from_attributes=True)


class QueryAnalyticsApplicationBreakdown(BaseModel):
    application_name: Optional[str]
    execution_count: int

    model_config = ConfigDict(from_attributes=True)


class QueryAnalyticsItem(BaseModel):
    sources: List[str] = []
    pg_query_id: Optional[str] = None
    query_hashes: List[str] = []
    query_texts: List[str] = []
    activity_executions: int = 0
    statements_calls: Optional[int] = None
    metrics_source: str = "activity"
    query_signature: str
    query_preview: str
    query_hash: Optional[str]
    execution_count: int
    avg_duration_ms: Optional[float]
    max_duration_ms: Optional[float]
    min_duration_ms: Optional[float]
    total_duration_ms: Optional[float]
    unique_users: int
    user_breakdown: List[QueryAnalyticsUserBreakdown]
    unique_applications: int
    application_breakdown: List[QueryAnalyticsApplicationBreakdown]
    first_seen: datetime
    last_seen: datetime

    model_config = ConfigDict(from_attributes=True)


class QueryAnalyticsTimelinePoint(BaseModel):
    source: str = "activity"
    interval_start: Optional[datetime] = None
    timestamp: datetime
    execution_count: int
    avg_duration_ms: Optional[float]

    model_config = ConfigDict(from_attributes=True)


class QueryAnalyticsFilters(BaseModel):
    users: List[Optional[str]]
    applications: List[Optional[str]]
    states: List[Optional[str]]

    model_config = ConfigDict(from_attributes=True)


class QueryAnalyticsResponse(BaseModel):
    database_id: UUID
    database_name: str
    start_at: datetime
    end_at: datetime
    items: List[QueryAnalyticsItem]
    total: int
    timeline: List[QueryAnalyticsTimelinePoint]
    filters: QueryAnalyticsFilters

    model_config = ConfigDict(from_attributes=True)


class QueryExecutionHistoryItem(BaseModel):
    source: str = "activity"
    calls: Optional[int] = None
    calls_delta: Optional[int] = None
    total_exec_time_delta_ms: Optional[float] = None
    user_id: Optional[int] = None
    is_toplevel: Optional[bool] = None
    statement_data: Optional[dict] = None
    collected_at: datetime
    duration_ms: Optional[float]
    user_name: Optional[str]
    application_name: Optional[str]
    rows_returned: Optional[int]

    model_config = ConfigDict(from_attributes=True)


class QueryExecutionHistoryResponse(BaseModel):
    query_hash: str
    query_preview: str
    items: List[QueryExecutionHistoryItem]

    model_config = ConfigDict(from_attributes=True)


class QueryContextExecution(BaseModel):
    source: str = "activity"
    statement_data: Optional[dict] = None
    collected_at: datetime
    duration_ms: Optional[float]
    query: str
    user_name: Optional[str]
    application_name: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class QueryContextServerMetrics(BaseModel):
    cpu_percent: Optional[float]
    ram_percent: Optional[float]
    disk_percent: Optional[float]
    read_bytes: Optional[int]
    write_bytes: Optional[int]
    cpu_stale: Optional[bool] = False
    ram_stale: Optional[bool] = False
    disk_stale: Optional[bool] = False
    io_stale: Optional[bool] = False

    model_config = ConfigDict(from_attributes=True)


class QueryContextDatabaseConnections(BaseModel):
    active: Optional[int]
    idle: Optional[int]
    idle_in_transaction: Optional[int]
    waiting: Optional[int]

    model_config = ConfigDict(from_attributes=True)


class QueryContextIndex(BaseModel):
    index_id: int
    index_name: str
    index_type: str
    definition: str
    is_unique: bool
    is_primary: bool
    size_bytes: Optional[int]
    scan_qt: Optional[int]
    hit_rate: Optional[float]

    model_config = ConfigDict(from_attributes=True)


class QueryContextColumn(BaseModel):
    column_id: int
    name: str
    data_type: str
    is_nullable: bool
    n_distinct: Optional[float]
    null_fraction: Optional[float]
    avg_width: Optional[int]

    model_config = ConfigDict(from_attributes=True)


class QueryContextTable(BaseModel):
    table_id: int
    schema_name: str
    table_name: str
    n_live_tup: Optional[int]
    n_dead_tup: Optional[int]
    seq_scan: Optional[int]
    idx_scan: Optional[int]
    last_vacuum: Optional[datetime]
    last_autovacuum: Optional[datetime]
    last_analyze: Optional[datetime]
    last_autoanalyze: Optional[datetime]
    size_bytes: Optional[int]
    indexes: List[QueryContextIndex]
    columns: List[QueryContextColumn]

    model_config = ConfigDict(from_attributes=True)


class QueryContextLock(BaseModel):
    table_name: Optional[str] = None
    holder_pid: int
    type: str
    mode: str
    is_granted: Optional[bool] = True
    query_preview: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class QueryContextResponse(BaseModel):
    execution: QueryContextExecution
    server_metrics: QueryContextServerMetrics
    database_connections: QueryContextDatabaseConnections
    tables: List[QueryContextTable]
    locks: List[QueryContextLock] = []

    model_config = ConfigDict(from_attributes=True)
