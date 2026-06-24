from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DatabaseCreate(BaseModel):
    server_id: UUID
    db_name: str


class DatabaseCreatedResponse(BaseModel):
    message: str
    id: UUID


class DatabaseListItem(BaseModel):
    id: UUID
    server_id: UUID
    name: str
    status: bool

    model_config = ConfigDict(from_attributes=True)


class DatabaseStatsResponse(BaseModel):
    database_id: UUID
    table_count: int
    index_count: int
    view_count: int
    size_bytes: int | None
    index_hit_rate: float | None

    model_config = ConfigDict(from_attributes=True)


class UptimeResponse(BaseModel):
    database_id: UUID
    uptime_formatted: str
    uptime_seconds: int
    postmaster_start_time: str

    model_config = ConfigDict(from_attributes=True)
