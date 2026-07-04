from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.tags.models import TagResponse


class DocBase(BaseModel):
    description: Optional[str] = Field(None, description="Documentation text")

class DocWithTagsBase(DocBase):
    tags: List[TagResponse] = Field(default_factory=list)

# Database
class DatabaseDocPut(DocBase):
    owner: Optional[str] = Field(None, description="Owner/Team responsible")
    classification: Optional[str] = Field("internal", description="Data classification level")

class DatabaseDocResponse(DocWithTagsBase, DatabaseDocPut):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: Optional[datetime] = None

# Schema
class SchemaDocPut(DocBase):
    owner: Optional[str] = Field(None, description="Owner/Team responsible")
    classification: Optional[str] = Field("internal", description="Data classification level")

class SchemaDocResponse(DocWithTagsBase, SchemaDocPut):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: Optional[datetime] = None

# Table
class TableDocPut(DocBase):
    owner: Optional[str] = Field(None, description="Owner/Team responsible")
    classification: Optional[str] = Field("internal", description="Data classification level")

class TableDocResponse(DocWithTagsBase, TableDocPut):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: Optional[datetime] = None

# Column
class ColumnDocPut(DocBase):
    is_pii: bool = Field(False, description="Whether this column contains Personally Identifiable Information")
    sample_values: Optional[str] = Field(None, description="Example values for this column")

class ColumnDocResponse(DocWithTagsBase, ColumnDocPut):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: Optional[datetime] = None

# Index
class IndexDocPut(DocBase):
    pass

class IndexDocResponse(DocWithTagsBase, IndexDocPut):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: Optional[datetime] = None
