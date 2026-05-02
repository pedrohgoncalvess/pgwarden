from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Name of the tag")
    description: Optional[str] = Field(default=None, max_length=255, description="Optional description of the tag")
    color: Optional[str] = Field(default="#6366F1", description="Hex color code for the tag")


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    color: Optional[str] = None


class TagResponse(TagBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., alias="public_id")
    created_at: datetime
