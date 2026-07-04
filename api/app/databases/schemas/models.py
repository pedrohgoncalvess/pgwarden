from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    status_code: int
    message: str
    details: Optional[str] = None


class SchemaColumnResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    data_type: str
    is_nullable: bool
    default_value: Optional[str] = None
    is_unique: bool
    ordinal_position: int
    fk_table_id: Optional[UUID] = None
    fk_column_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class SchemaIndexResponse(BaseModel):
    id: UUID
    name: str
    type: str
    definition: str
    is_unique: bool
    is_primary: bool
    columns: List[str]  # e.g., column names

    model_config = ConfigDict(from_attributes=True)


class SchemaTableResponse(BaseModel):
    id: UUID
    schema_name: str
    name: str
    description: Optional[str] = None
    columns: List[SchemaColumnResponse] = []
    indexes: List[SchemaIndexResponse] = []

    model_config = ConfigDict(from_attributes=True)


class SchemaResponse(BaseModel):
    id: UUID
    tables: List[SchemaTableResponse]

    model_config = ConfigDict(from_attributes=True)
