"""Public project and key administration contracts."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectSettings(BaseModel):
    """Optional key lifetime and automatic rotation policies, in days."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    key_expiration_days: int | None = Field(default=None, ge=1, le=3650)
    rotation_interval_days: int | None = Field(default=None, ge=1, le=3650)
    rotation_grace_hours: int = Field(default=24, ge=0, le=168)

    @model_validator(mode="after")
    def validate_rotation(self) -> Self:
        """Keep the current key valid long enough for scheduled handoff."""
        if self.rotation_interval_days is not None:
            if self.rotation_grace_hours == 0:
                raise ValueError("Automatic rotation requires a positive grace period")
            if (
                self.key_expiration_days is not None
                and self.rotation_interval_days >= self.key_expiration_days
            ):
                raise ValueError("Rotation must occur before key expiration")
        return self


class ProjectView(ProjectSettings):
    """Project settings and ingestion activity without credentials."""

    id: UUID
    created_at: datetime
    next_rotation_at: datetime | None
    last_event_at: datetime | None


class KeyView(BaseModel):
    """Safe key metadata; full credentials are excluded."""

    id: UUID
    prefix: str
    created_at: datetime
    expires_at: datetime | None
    retire_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None


class IssuedKey(BaseModel):
    """A newly issued key, returned only by creation or rotation."""

    key: str
    metadata: KeyView


class ProjectCreated(BaseModel):
    """Project and its initial ingestion credential."""

    project: ProjectView
    credential: IssuedKey


class RotationRequest(BaseModel):
    """An optional overlap; zero invalidates every previous key immediately."""

    model_config = ConfigDict(extra="forbid")
    grace_hours: int = Field(default=0, ge=0, le=168)
