from uuid import UUID

from fastapi import APIRouter

from app.schema.models import SchemaResponse
from app.schema.services import get_database_schema
from database.connection import DatabaseConnection


router = APIRouter(
    prefix="/schema",
    tags=["schema"]
)

@router.get(
    "/{database_id}",
    response_model=SchemaResponse,
    summary="Get database schema metadata",
    description="Returns the full, tracked schema definition of the requested database. This includes tables, columns, constraints, and indexes. Does NOT return actual table data.",
)
async def get_schema(database_id: UUID):
    async with DatabaseConnection() as conn:
        return await get_database_schema(conn, database_id)
