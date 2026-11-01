"""Generate initial credentials and allow authenticated password changes."""
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select

from app.auth.services import get_current_user, pwd_context, verify_password
from database.connection import DatabaseConnection
from database.models.base import Refresh, User

router = APIRouter(prefix='/auth', tags=['auth'])


def generate_password() -> str:
    """Generate eight random characters including letters, digits, and symbols."""
    groups = (string.ascii_lowercase, string.ascii_uppercase,
              string.digits, '!@#$%&*+-=?')
    characters = [secrets.choice(group) for group in groups]
    alphabet = ''.join(groups)
    characters.extend(secrets.choice(alphabet) for _ in range(4))
    secrets.SystemRandom().shuffle(characters)
    return ''.join(characters)


class PasswordChange(BaseModel):
    """Validate the old credential and the confirmed replacement."""

    model_config = ConfigDict(extra='forbid')
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)
    confirm_password: str = Field(min_length=8, max_length=72)

    @model_validator(mode='after')
    def validate_passwords(self) -> 'PasswordChange':
        """Preserve password whitespace and reject mismatches or bcrypt overflow."""
        if self.new_password != self.confirm_password:
            raise ValueError('The new password and confirmation must match')
        if any(len(value.encode('utf-8')) > 72 for value in (
            self.current_password, self.new_password, self.confirm_password
        )):
            raise ValueError('Passwords must not exceed 72 bytes')
        if self.current_password == self.new_password:
            raise ValueError('The new password must differ from the current one')
        return self


@router.post('/password', status_code=204)
async def change_password(
    body: PasswordChange, current_user: User = Depends(get_current_user)
) -> Response:
    """Change only the authenticated user's password after checking the old one."""
    async with DatabaseConnection() as connection:
        user = (await connection.execute(
            select(User).where(User.id == current_user.id).with_for_update()
        )).scalar_one_or_none()
        if user is None or user.deleted_at is not None:
            raise HTTPException(401, 'Account unavailable')
        if not verify_password(body.current_password, user.password):
            raise HTTPException(400, 'Current password is incorrect')
        user.password = pwd_context.hash(body.new_password)
        await connection.execute(delete(Refresh).where(Refresh.user_id == user.id))
        await connection.commit()
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})
