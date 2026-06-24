from typing import List, Union
import asyncio
import ssl

from fastapi import APIRouter, Depends, HTTPException
import asyncpg

from app.servers.models import (
    ServerCreate, ServerListItem, ServerDatabaseItem,
    ServerCreatedResponse, ConnectionTestSuccess, ConnectionTestError, ServerTest,
)
from app.common.models import COMMON_RESPONSES, ErrorMessage
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
        return ConnectionTestError(
            status="error",
            code="Invalid port",
            detail=f"Port '{server_in.port}' is not a number. Use the PostgreSQL TCP port, usually 5432.",
        )

    if port < 1 or port > 65535:
        return ConnectionTestError(
            status="error",
            code="Invalid port",
            detail=f"Port '{port}' is outside the valid TCP range. Use a value between 1 and 65535.",
        )

    conn = None
    try:
        conn = await asyncpg.connect(
            host=server_in.host,
            port=port,
            user=server_in.username,
            password=server_in.password,
            ssl=server_in.ssl_mode,
            timeout=10,
        )
        version = await conn.fetchval("SELECT 'PostgreSQL ' || current_setting('server_version')")
        return ConnectionTestSuccess(status="success", version=version)

    except asyncpg.InvalidPasswordError:
        return ConnectionTestError(
            status="error",
            code="Authentication failed",
            detail=f"PostgreSQL rejected the password for user '{server_in.username}'. Verify the username and password.",
        )

    except asyncpg.InvalidAuthorizationSpecificationError:
        return ConnectionTestError(
            status="error",
            code="Authentication failed",
            detail=f"PostgreSQL rejected user '{server_in.username}'. Check the username, password, and pg_hba.conf rules for this host.",
        )

    except asyncpg.InvalidCatalogNameError:
        return ConnectionTestError(
            status="error",
            code="Database not found",
            detail="PostgreSQL accepted the network connection, but the default database for this user does not exist.",
        )

    except asyncpg.CannotConnectNowError:
        return ConnectionTestError(
            status="error",
            code="Server starting up",
            detail="PostgreSQL is reachable, but it is not accepting connections yet. Try again after startup or recovery finishes.",
        )

    except asyncpg.TooManyConnectionsError:
        return ConnectionTestError(
            status="error",
            code="Too many connections",
            detail="PostgreSQL is reachable, but it has no free connection slots. Close idle sessions or increase max_connections.",
        )

    except ssl.SSLError:
        return ConnectionTestError(
            status="error",
            code="SSL error",
            detail=f"Could not complete the SSL handshake with {server_in.host}:{port}. Try another SSL mode or check the server certificate settings.",
        )

    except OSError as e:
        error_str = str(e).lower()

        if "name or service not known" in error_str or "getaddrinfo failed" in error_str or "temporary failure in name resolution" in error_str:
            return ConnectionTestError(
                status="error",
                code="DNS resolution failed",
                detail=f"Could not resolve host '{server_in.host}'. Check the hostname, DNS record, or use an IP address.",
            )

        if "connection refused" in error_str or "connect call failed" in error_str:
            return ConnectionTestError(
                status="error",
                code="Connection refused",
                detail=f"{server_in.host}:{port} refused the connection. Confirm PostgreSQL is running and listening on this address and port.",
            )

        if "timed out" in error_str or "timeout" in error_str:
            return ConnectionTestError(
                status="error",
                code="Connection timeout",
                detail=f"Connection to {server_in.host}:{port} timed out. Check firewall rules, routing, VPN access, and PostgreSQL listen_addresses.",
            )

        if "network is unreachable" in error_str or "no route to host" in error_str:
            return ConnectionTestError(
                status="error",
                code="Network unreachable",
                detail=f"The API container cannot reach {server_in.host}:{port}. Check Docker networking, VPN access, and firewall routes.",
            )

        if "connection reset" in error_str:
            return ConnectionTestError(
                status="error",
                code="Connection reset",
                detail=f"The server closed the connection while testing {server_in.host}:{port}. Check SSL mode, pg_hba.conf, and server logs.",
            )

        return ConnectionTestError(
            status="error",
            code="Network error",
            detail=f"Could not reach {server_in.host}:{port}. Network error: {e}",
        )

    except asyncio.TimeoutError:
        return ConnectionTestError(
            status="error",
            code="Connection timeout",
            detail=f"Connection to {server_in.host}:{port} timed out after 10 seconds. Check firewall rules, routing, VPN access, and PostgreSQL listen_addresses.",
        )

    except asyncpg.PostgresError as e:
        message = getattr(e, "message", str(e))
        sqlstate = getattr(e, "sqlstate", None)
        return ConnectionTestError(
            status="error",
            code="PostgreSQL error",
            detail=f"PostgreSQL returned {sqlstate or 'an error'}: {message}",
        )

    except ValueError as e:
        return ConnectionTestError(
            status="error",
            code="Invalid connection settings",
            detail=f"Could not use the provided connection settings: {e}",
        )

    except Exception as e:
        return ConnectionTestError(
            status="error",
            code="Unknown error",
            detail=f"Unexpected error while testing {server_in.host}:{port}: {e}",
        )
    finally:
        if conn is not None:
            await conn.close()


@router.delete(
    "/{server_id}",
    status_code=204,
    summary="Delete a registered server",
    description=(
        "Permanently deletes a server and all data collected under it "
        "(databases, sessions, locks, metrics, schemas, configs, tags). "
        "This action is irreversible."
    ),
    responses={
        404: {"model": ErrorMessage, "description": "Server not found"},
        **COMMON_RESPONSES,
    },
)
async def delete_server(server_id: str):
    async with DatabaseConnection() as conn:
        repo = ServerRepository(conn)
        server = await repo.find_one_by(public_id=server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")
        await repo.delete(server.id)
