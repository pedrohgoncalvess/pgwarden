import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from passlib.context import CryptContext

from app.auth.router import router as auth_router
from app.schemas.router import router as schema_router
from app.databases.router import router as database_router
from app.servers.router import router as server_router
from app.databases.sessions.router import router as sessions_router
from app.databases.locks.router import router as locks_router
from app.databases.configs.router import router as db_config_router
from app.servers.config.router import router as srv_config_router
from app.servers.metrics.router import router as srv_metrics_router
from app.tags.router import router as tags_router
from app.docs.router import router as docs_router
from app.schemas.exceptions import BaseAppException
from database.connection import DatabaseConnection
from database.models.base import User
from database.operations.base.user import UserRepository


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_cors_origins() -> list[str]:
    origins = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):

    if os.getenv("IS_TESTING") == "1":
        yield
        return

    email = os.getenv("PGWARDEN_EMAIL")
    password = os.getenv("PGWARDEN_PASSWORD")
    hashed_password = pwd_context.hash(password)

    try:
        async with DatabaseConnection() as conn:
            user_repo = UserRepository(conn)
            existing_user = await user_repo.find_by_email(email)
            if not existing_user:
                admin_user = User(
                    email=email,
                    password=hashed_password,
                    name="Admin",
                    is_admin=True,
                )
                await user_repo.insert(admin_user)
                print(f"Admin user {email} created successfully.")
    except Exception as e:
        print(f"Failed to initialize admin user: {e}")
        
    yield

tags_metadata = [
    {
        "name": "auth",
        "description": "Authentication and authorization endpoints. Handles login and JWT token refresh.",
    },
    {
        "name": "servers",
        "description": "Manage registered PostgreSQL servers. Connection credentials are encrypted and stored securely.",
    },
    {
        "name": "databases",
        "description": "Manage monitored databases linked to the registered servers.",
    },
    {
        "name": "schemas",
        "description": "Expose the currently collected schema metadata (tables, columns, indexes).",
    },
    {
        "name": "sessions",
        "description": "Real-time session monitoring via Server-Sent Events.",
    },
    {
        "name": "locks",
        "description": "Real-time lock monitoring via Server-Sent Events.",
    },
    {
        "name": "tags",
        "description": "Manage classification tags scoped to a server.",
    },
    {
        "name": "database doc",
        "description": "Documentation for managed databases.",
    },
    {
        "name": "schema doc",
        "description": "Documentation for PostgreSQL schemas.",
    },
    {
        "name": "table doc",
        "description": "Documentation for tables.",
    },
    {
        "name": "column doc",
        "description": "Documentation for columns, including PII classification.",
    },
    {
        "name": "index doc",
        "description": "Documentation for indexes.",
    },
]

app = FastAPI(
    title="PGWarden API",
    description="""
    PGWarden API provides endpoints for managing monitored PostgreSQL servers and databases. 
    """,
    version="0.1.0",
    openapi_tags=tags_metadata,
    swagger_ui_parameters={
        "displayRequestDuration": True,
        "defaultModelsExpandDepth": -1,
    },
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(BaseAppException)
async def app_exception_handler(request: Request, exc: BaseAppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "message": exc.message,
            "details": exc.details
        }
    )

app.include_router(auth_router, prefix="/v1")
app.include_router(schema_router, prefix="/v1")
app.include_router(database_router, prefix="/v1")
app.include_router(server_router, prefix="/v1")
app.include_router(sessions_router, prefix="/v1")
app.include_router(locks_router, prefix="/v1")
app.include_router(db_config_router, prefix="/v1")
app.include_router(srv_config_router, prefix="/v1")
app.include_router(srv_metrics_router, prefix="/v1")
app.include_router(tags_router, prefix="/v1")
app.include_router(docs_router, prefix="/v1")
