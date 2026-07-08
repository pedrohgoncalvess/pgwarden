from fastapi import APIRouter, Depends, Query

from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES
from app.metadata.search.models import MetadataSearchResponse
from app.metadata.search.services import search_metadata
from database.connection import DatabaseConnection


router = APIRouter(
    prefix="/search",
    tags=["metadata search"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "",
    response_model=MetadataSearchResponse,
    summary="Search metadata and documentation",
    description="Hybrid search over metadata names, exact terms, fuzzy matches and documentation embeddings.",
    responses=COMMON_RESPONSES,
)
async def search_metadata_endpoint(
    q: str = Query(..., min_length=1, description="Search term"),
    database_id: str | None = Query(default=None, description="Optional database public id filter"),
    server_id: str | None = Query(default=None, description="Optional server public id filter"),
    limit: int = Query(default=25, ge=1, le=100),
    semantic: bool = Query(default=True, description="Enable semantic search with embeddings"),
):
    async with DatabaseConnection() as conn:
        return await search_metadata(
            conn,
            query=q,
            database_id=database_id,
            server_id=server_id,
            limit=limit,
            semantic=semantic,
        )
