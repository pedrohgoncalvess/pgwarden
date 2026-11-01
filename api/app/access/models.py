from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator, field_validator
from typing import Literal

Permission = Literal['alerts.read', 'alerts.configure', 'documentation.read',
                     'documentation.configure', 'schedulers.read', 'schedulers.configure']


class RoleInput(BaseModel):
    """Explicit resource and capability grants for a role."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    permissions: list[Permission] = Field(default_factory=list)
    project_ids: list[UUID] = Field(default_factory=list)
    server_ids: list[UUID] = Field(default_factory=list)
    database_ids: list[UUID] = Field(default_factory=list)


class UserInput(BaseModel):
    """Administrator-supplied account identity and assignment."""
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=50)
    email: EmailStr = Field(max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=72)
    is_admin: bool = False
    role_id: int | None = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Reject empty account names after trimming display whitespace."""
        if not value.strip():
            raise ValueError('Name must not be blank')
        return value.strip()

    @model_validator(mode='after')
    def require_role(self) -> "UserInput":
        """Require a role for ordinary accounts and bcrypt-safe passwords."""
        if not self.is_admin and self.role_id is None:
            raise ValueError('A non-administrator must have a role')
        if self.password and len(self.password.encode('utf-8')) > 72:
            raise ValueError('Password must not exceed 72 bytes')
        return self


class UserView(BaseModel):
    """Account fields safe to disclose to an administrator."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    is_admin: bool
    role_id: int | None


class UserCreated(UserView):
    """Reveal an automatically generated initial password only at creation."""

    generated_password: str | None = None
