"""Expose project names without granting access to ingestion administration."""
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.access.policy import access_context
from app.access.services import authorize_request
from app.projects.tables import project
from database.connection import DatabaseConnection

router = APIRouter(prefix='/catalog', dependencies=[Depends(authorize_request)])


@router.get('/projects')
async def list_visible_projects() -> list[dict]:
    """List only names and identifiers of accessible projects."""
    access = access_context()
    async with DatabaseConnection() as connection:
        query = select(project.c.id, project.c.name).order_by(project.c.name)
        if not access.admin:
            query = query.where(project.c.id.in_(list(access.projects)))
        return [dict(row) for row in (await connection.execute(query)).mappings()]
