from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

class ServerCreate(BaseModel):
    name: str
    host: str
    port: str
    username: str
    password: str
    ssl_mode: str = "prefer"
    ignore_patterns: Optional[List[str]] = None
    ignore_tables: Optional[List[str]] = None
    include_tables: Optional[List[str]] = None

class ServerDatabaseItem(BaseModel):
    id: UUID

    model_config = ConfigDict(from_attributes=True)

class ServerListItem(BaseModel):
    id: UUID
    name: str
    status: str
    databases: List[ServerDatabaseItem]

    model_config = ConfigDict(from_attributes=True)
