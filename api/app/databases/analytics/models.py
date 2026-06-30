from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TableSizePoint(BaseModel):
    collected_at: datetime
    table_id: int
    schema_name: str
    table_name: str
    size_bytes: int

    model_config = ConfigDict(from_attributes=True)


class DatabaseSizePoint(BaseModel):
    collected_at: datetime
    size_bytes: int

    model_config = ConfigDict(from_attributes=True)


class AnalyticsTableFilterItem(BaseModel):
    id: int
    schema_name: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class AnalyticsDataResponse(BaseModel):
    database_id: UUID
    database_name: str
    database_size_history: List[DatabaseSizePoint]
    table_size_history: List[TableSizePoint]
    tables: List[AnalyticsTableFilterItem]

    model_config = ConfigDict(from_attributes=True)


class AnalyticsIndexFilterItem(BaseModel):
    id: int
    table_id: int
    schema_name: str
    table_name: str
    index_name: str
    index_type: str
    is_unique: bool
    is_primary: bool

    model_config = ConfigDict(from_attributes=True)


class AnalyticsTableFilterForIndex(BaseModel):
    id: int
    schema_name: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class IndexMetricPoint(BaseModel):
    collected_at: datetime
    index_id: int
    size_bytes: int
    scan_qt: Optional[int]
    tup_read_qt: Optional[int]
    tup_fetch_qt: Optional[int]
    blks_read: Optional[int]
    blks_hit: Optional[int]

    model_config = ConfigDict(from_attributes=True)


class IndexAnalyticsKpi(BaseModel):
    total_indexes: int
    total_size_bytes: int
    avg_hit_rate: Optional[float]
    avg_scan_qt: Optional[float]
    unused_indexes: int
    unique_indexes: int
    primary_indexes: int

    model_config = ConfigDict(from_attributes=True)


class IndexAnalyticsTimelinePoint(BaseModel):
    collected_at: datetime
    total_size_bytes: int
    total_scans: int
    avg_hit_rate: Optional[float]

    model_config = ConfigDict(from_attributes=True)


class IndexAnalyticsItem(BaseModel):
    index_id: int
    table_id: int
    schema_name: str
    table_name: str
    index_name: str
    index_type: str
    is_unique: bool
    is_primary: bool
    latest_size_bytes: int
    latest_scan_qt: Optional[int]
    latest_tup_read_qt: Optional[int]
    latest_tup_fetch_qt: Optional[int]
    latest_blks_read: Optional[int]
    latest_blks_hit: Optional[int]
    hit_rate: Optional[float]
    total_scans: Optional[int]
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    history: List[IndexMetricPoint]

    model_config = ConfigDict(from_attributes=True)


class IndexAnalyticsResponse(BaseModel):
    database_id: UUID
    database_name: str
    start_at: datetime
    end_at: datetime
    kpis: IndexAnalyticsKpi
    timeline: List[IndexAnalyticsTimelinePoint]
    items: List[IndexAnalyticsItem]
    tables: List[AnalyticsTableFilterForIndex]
    indexes: List[AnalyticsIndexFilterItem]

    model_config = ConfigDict(from_attributes=True)
