import os
import asyncio
from contextlib import suppress
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from passlib.context import CryptContext

from app.security.default_credentials import sync_default_credentials_notification
from app.databases.schemas.exceptions import BaseAppException
from app.openapi import tags_metadata
from app.routes import register_routes
from app.projects.rotation import run_rotation_worker
from database.connection import DatabaseConnection
from database.models.base import User
from database.operations.base.user import UserRepository


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_cors_origins() -> list[str]:
    """Read the configured browser origins."""
    origins = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize the administrator and manage the key rotation worker."""

    if os.getenv("IS_TESTING") == "1":
        yield
        return

    email = os.getenv("PGWARDEN_EMAIL")
    password = os.getenv("PGWARDEN_PASSWORD")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
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
            await sync_default_credentials_notification(
                conn,
                email,
                password,
                db_user,
                db_password,
            )
    except Exception as e:
        print(f"Failed to initialize admin user: {e}")

    rotation_task = asyncio.create_task(run_rotation_worker())
    try:
        yield
    finally:
        rotation_task.cancel()
        with suppress(asyncio.CancelledError):
            await rotation_task
        await DatabaseConnection.shutdown()


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
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(BaseAppException)
async def app_exception_handler(request: Request, exc: BaseAppException) -> JSONResponse:
    """Return the existing application error contract."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.message, "details": exc.details},
    )


register_routes(app)
