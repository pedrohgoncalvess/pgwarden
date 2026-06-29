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
