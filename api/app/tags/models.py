from typing import Literal, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Name of the tag")
    description: Optional[str] = Field(default=None, description="Optional description of the tag")
    color: Optional[str] = Field(default="#6366F1", description="Hex color code for the tag")
    type: str = Field(default="default", min_length=1, max_length=20, description="Tag category")


class TagCreate(TagBase):
    server_id: UUID = Field(..., description="Server that owns this tag")


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = None
    color: Optional[str] = None
    type: Optional[str] = Field(None, min_length=1, max_length=20)


class TagResponse(TagBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., validation_alias="public_id")
    created_at: datetime


TagScope = Literal["object", "doc"]
TagTargetType = Literal["database", "schema", "table", "column", "index", "native_query"]


class TagAssignmentCreate(BaseModel):
    scope: TagScope
    target_type: TagTargetType
    target_id: Optional[UUID] = Field(default=None, description="Public id for database, table, column or index targets")
    database_id: Optional[UUID] = Field(default=None, description="Database public id for schema and native query targets")
    schema_name: Optional[str] = Field(default=None, description="Schema name for schema documentation targets")
    query_hash: Optional[str] = Field(default=None, description="Native query hash for query targets")


class TagAssignmentDelete(TagAssignmentCreate):
    pass


class TagAssignmentResponse(BaseModel):
    tag: TagResponse
    scope: TagScope
    target_type: TagTargetType
    target_id: Optional[str] = None
    target_label: str
    database_id: Optional[str] = None
    query_hash: Optional[str] = None
    created_at: datetime
