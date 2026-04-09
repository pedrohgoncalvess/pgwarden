from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: UUID


class TokenDetails(BaseModel):
    token: str
    expires: str


class AuthResponse(BaseModel):
    access_token: TokenDetails
    refresh_token: TokenDetails
    token_type: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_verified: bool
    is_admin: bool