import uuid
from datetime import timedelta, datetime

from fastapi import APIRouter, HTTPException
from starlette import status

from app.auth.models import UserLogin, RefreshTokenRequest, AuthResponse
from app.auth.services import verify_password, create_access_token
from database.connection import DatabaseConnection
from database.models.base import Refresh
from database.operations.base import RefreshRepository
from database.operations.base.user import UserRepository


router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

ACCESS_TOKEN_EXPIRE_MINUTES = 90
REFRESH_TOKEN_EXPIRE_MINUTES = 300

@router.post(
    "",
    response_model=AuthResponse,
    summary="User Login",
    description="Authenticates a user via email and password, returning an access token and a refresh token."
)
async def login(user_auth: UserLogin):
    async with DatabaseConnection() as conn:
        user_repository = UserRepository(conn)
        refresh_repository = RefreshRepository(conn)

        user = await user_repository.find_by_email(user_auth.email)

        if not user or not verify_password(user_auth.password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email or password incorrect.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        refresh_token = uuid.uuid4()
        _ = await refresh_repository.insert(
            Refresh(
                token=str(refresh_token),
                user_id=user.id,
            )
        )

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email}, expires_delta=access_token_expires
        )

        access_token_expires_at = (datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
        refresh_token_expires_at = (datetime.now() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "access_token": {"token": access_token, "expires":access_token_expires_at },
            "refresh_token": {"token": str(refresh_token), "expires": refresh_token_expires_at},
            "token_type": "bearer"
        }


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Refresh Authentication Token",
    description="Exchanges an active refresh token for a new access token and a new refresh token."
)
async def refresh_token(payload: RefreshTokenRequest):
    async with DatabaseConnection() as conn:
        refresh_repository = RefreshRepository(conn)
        user_repository = UserRepository(conn)

        refresh = await refresh_repository.find_by_token(payload.refresh_token)

        if not refresh:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token.",
            )

        user = await user_repository.find_by_id(refresh.user_id)

        if refresh.inserted_at + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES) < datetime.utcnow() or not refresh.used:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired.",
            )

        upt_data = {"used": True}
        await refresh_repository.update(refresh.id, upt_data)

        new_refresh_token = str(uuid.uuid4())

        await refresh_repository.insert(
            Refresh(
                token=new_refresh_token,
                user_id=user.id,
            )
        )

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email},
            expires_delta=access_token_expires,
        )

        access_token_expires_at = (datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).strftime(
            "%Y-%m-%d %H:%M:%S")
        refresh_token_expires_at = (datetime.now() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)).strftime(
            "%Y-%m-%d %H:%M:%S")

        return {
            "access_token": {
                "token": access_token,
                "expires": access_token_expires_at,
            },
            "refresh_token": {
                "token": str(new_refresh_token),
                "expires": refresh_token_expires_at,
            },
            "token_type": "bearer",
        }
