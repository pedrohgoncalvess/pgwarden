from typing import Literal, Optional

from pydantic import BaseModel


SearchObjectType = Literal["database", "schema", "table", "column", "index", "tag"]


class MetadataSearchResult(BaseModel):
    type: SearchObjectType
    id: str
    database_id: Optional[str] = None
    database_name: Optional[str] = None
    schema_name: Optional[str] = None
    table_id: Optional[str] = None
    table_name: Optional[str] = None
    name: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    exact_score: float
    fuzzy_score: float
    vector_score: float
    score: float


class MetadataSearchResponse(BaseModel):
    query: str
    results: list[MetadataSearchResult]
