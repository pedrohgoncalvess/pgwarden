from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class SchemaHistoryItem(BaseModel):
    id: str
    type: Literal["table", "column", "index"]
    action: Literal["added", "removed", "altered"]
    schema_name: Optional[str] = None
    table_name: Optional[str] = None
    column_name: Optional[str] = None
    index_name: Optional[str] = None
    object_id: Optional[UUID] = None
    table_id: Optional[UUID] = None
    changed_at: datetime
    changed_by: Optional[int] = None
    details: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SchemaHistoryResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[SchemaHistoryItem]

    model_config = ConfigDict(from_attributes=True)
