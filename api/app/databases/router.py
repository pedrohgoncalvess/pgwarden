from typing import List
from fastapi import APIRouter, HTTPException, Depends

from app.databases.models import DatabaseListItem, DatabaseCreate, DatabaseCreatedResponse
from app.common.models import COMMON_RESPONSES, ErrorMessage
from database.connection import DatabaseConnection
from database.operations.metadata.database import DatabaseRepository
from database.operations.collector.server import ServerRepository
from database.models.metadata.database import Database
from utils import encrypt, decrypt
from app.auth.services import get_current_user


router = APIRouter(
    prefix="/databases",
    tags=["databases"],
    dependencies=[Depends(get_current_user)],
)

@router.post(
    "/",
    response_model=DatabaseCreatedResponse,
    summary="Register a new managed database",
    description="Registers a new monitored database and links it to an existing PostgreSQL server. The database name is securely encrypted.",
    responses={
        404: {"model": ErrorMessage, "description": "Server not found"},
        **COMMON_RESPONSES
    }
)
async def create_database(db_in: DatabaseCreate):
    async with DatabaseConnection() as conn:
        server_repo = ServerRepository(conn)
        db_repo = DatabaseRepository(conn)

        server = await server_repo.find_one_by(public_id=db_in.server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

        new_db = Database(
            server_id=server.id,
            db_name=encrypt(db_in.db_name)
        )

        saved_db = await db_repo.insert(new_db)
        return DatabaseCreatedResponse(message="Database created successfully", id=saved_db.public_id)

@router.get(
    "/",
    response_model=List[DatabaseListItem],
    summary="List all managed databases",
    description="Returns a list of all managed databases and their connection status. Includes both active and soft-deleted databases.",
    responses=COMMON_RESPONSES
)
async def list_databases():
    async with DatabaseConnection() as conn:
        repo = DatabaseRepository(conn)
        databases = await repo.find_all()

        return [
            DatabaseListItem(
                id=db.public_id,
                name=decrypt(db.db_name),
                status=db.deleted_at is None
            )
            for db in databases
        ]
