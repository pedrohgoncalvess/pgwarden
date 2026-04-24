from typing import List, Union
import asyncio

from fastapi import APIRouter, Depends
import asyncpg

from app.servers.models import (
    ServerCreate, ServerListItem, ServerDatabaseItem,
    ServerCreatedResponse, ConnectionTestSuccess, ConnectionTestError, ServerTest,
)
from app.common.models import COMMON_RESPONSES
from database.connection import DatabaseConnection
from database.operations.collector.server import ServerRepository
from database.operations.metadata.database import DatabaseRepository
from database.models.collector.server import Server
from utils import encrypt
from app.auth.services import get_current_user


router = APIRouter(
    prefix="/servers",
    tags=["servers"],
    dependencies=[Depends(get_current_user)],
)

@router.post(
    "/",
    response_model=ServerCreatedResponse,
    summary="Register a new PostgreSQL server",
    description="Registers a new server. Sensitive connection credentials (host, port, username, password) are securely encrypted before being stored.",
    responses=COMMON_RESPONSES
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
        return ServerCreatedResponse(message="Server created successfully", id=saved_server.public_id)

@router.get(
    "/",
    response_model=List[ServerListItem],
    summary="List all registered servers",
    description="Returns a list of all monitored servers along with their current status and a list of linked databases. Decrypted credentials are never exposed.",
    responses=COMMON_RESPONSES
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


@router.post(
    "/test-connection",
    response_model=Union[ConnectionTestSuccess, ConnectionTestError],
    summary="Test a PostgreSQL connection",
    description="Receives connection credentials and tests connectivity to the PostgreSQL server. No data is stored.",
    responses=COMMON_RESPONSES
)
async def test_connection(server_in: ServerTest):
    try:
        port = int(server_in.port)
    except ValueError:
        return ConnectionTestError(status="error", code="Invalid port", detail=f"Port '{server_in.port}' is not a valid number.")

    try:
        conn = await asyncpg.connect(
            host=server_in.host,
            port=port,
            user=server_in.username,
            password=server_in.password,
            ssl=server_in.ssl_mode,
            timeout=10,
        )
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        return ConnectionTestSuccess(status="success", version=version)

    except asyncpg.InvalidAuthorizationSpecificationError:
        return ConnectionTestError(
            status="error",
            code="Authentication failed",
            detail=f"Authentication failed for user '{server_in.username}'. Check username and password.",
        )

    except asyncpg.InvalidCatalogNameError:
        return ConnectionTestError(
            status="error",
            code="Database not found",
            detail="The specified database does not exist on this server.",
        )

    except OSError as e:
        error_str = str(e).lower()

        if "name or service not known" in error_str or "getaddrinfo failed" in error_str:
            return ConnectionTestError(
                status="error",
                code="DNS resolution failed",
                detail=f"Could not resolve host '{server_in.host}'. Check the hostname or IP address.",
            )

        if "connection refused" in error_str or "connect call failed" in error_str:
            return ConnectionTestError(
                status="error",
                code="Connection refused",
                detail=f"Connection refused at {server_in.host}:{port}. Verify the host, port, and that PostgreSQL is running.",
            )

        if "timed out" in error_str or "timeout" in error_str:
            return ConnectionTestError(
                status="error",
                code="Connection timeout",
                detail=f"Connection to {server_in.host}:{port} timed out. The server may be unreachable or blocked by a firewall.",
            )

        return ConnectionTestError(
            status="error",
            code="Network error",
            detail=f"Network error: {e}",
        )

    except asyncio.TimeoutError:
        return ConnectionTestError(
            status="error",
            code="Connection timeout",
            detail=f"Connection to {server_in.host}:{port} timed out after 10 seconds.",
        )

    except asyncpg.PostgresError as e:
        return ConnectionTestError(
            status="error",
            code="PostgreSQL error",
            detail=f"PostgreSQL error: {e.message}",
        )

    except Exception as e:
        return ConnectionTestError(
            status="error",
            code="Unknown error",
            detail=str(e),
        )
