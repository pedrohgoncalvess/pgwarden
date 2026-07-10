from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.tags.models import TagResponse


class DocBase(BaseModel):
    description: Optional[str] = Field(None, description="Documentation text")

class DocWithTagsBase(DocBase):
    tags: List[TagResponse] = Field(default_factory=list)

class DatabaseDocPut(DocBase):
    pass

class DatabaseDocResponse(DocWithTagsBase, DatabaseDocPut):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: Optional[datetime] = None

class SchemaDocPut(DocBase):
    pass

class SchemaDocResponse(DocWithTagsBase, SchemaDocPut):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: Optional[datetime] = None

class TableDocPut(DocBase):
    pass

class TableDocResponse(DocWithTagsBase, TableDocPut):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: Optional[datetime] = None

class ColumnDocPut(DocBase):
    is_pii: bool = Field(False, description="Whether this column contains Personally Identifiable Information")
    sample_values: Optional[str] = Field(None, description="Example values for this column")

class ColumnDocResponse(DocWithTagsBase, ColumnDocPut):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: Optional[datetime] = None

class IndexDocPut(DocBase):
    pass

class IndexDocResponse(DocWithTagsBase, IndexDocPut):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: Optional[datetime] = None
