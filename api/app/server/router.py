from typing import List

from fastapi import APIRouter

from app.server.models import ServerCreate, ServerListItem, ServerDatabaseItem
from database.connection import DatabaseConnection
from database.operations.collector.server import ServerRepository
from database.operations.metadata.database import DatabaseRepository
from database.models.collector.server import Server
from utils import encrypt


router = APIRouter(
    prefix="/server",
    tags=["server"]
)

@router.post(
    "/",
    summary="Register a new PostgreSQL server",
    description="Registers a new server. Sensitive connection credentials (host, port, username, password) are securely encrypted before being stored.",
)
async def create_server(server_in: ServerCreate):
    async with DatabaseConnection() as conn:
        repo = ServerRepository(conn)
        
        new_server = Server(
            name=server_in.name,
            host=encrypt(server_in.host),
            port=encrypt(server_in.port),
            username=encrypt(server_in.username),
            password=encrypt(server_in.password),
            ssl_mode=server_in.ssl_mode,
            ignore_patterns=server_in.ignore_patterns,
            ignore_tables=server_in.ignore_tables,
            include_tables=server_in.include_tables
        )
        
        saved_server = await repo.insert(new_server)
        return {"message": "Server created successfully", "id": saved_server.public_id}

@router.get(
    "/",
    response_model=List[ServerListItem],
    summary="List all registered servers",
    description="Returns a list of all monitored servers along with their current status and a list of linked databases. Decrypted credentials are never exposed.",
)
async def list_servers():
    async with DatabaseConnection() as conn:
        server_repo = ServerRepository(conn)
        db_repo = DatabaseRepository(conn)
        
        servers = await server_repo.find_all()
        databases = await db_repo.find_by(deleted_at=None)
        
        db_map = {}
        for db in databases:
            if db.server_id not in db_map:
                db_map[db.server_id] = []
            db_map[db.server_id].append(ServerDatabaseItem(id=db.public_id))
            
        result = []
        for s in servers:
            status = "error" if s.last_error else "healthy"
            if not s.last_seen_at:
                status = "pending"
                
            result.append(ServerListItem(
                id=s.public_id,
                name=s.name,
                status=status,
                databases=db_map.get(s.id, [])
            ))
            
        return result
