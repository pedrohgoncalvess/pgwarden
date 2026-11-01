"""Administrator-managed users and roles; no public registration."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.models import UserCreated, UserInput, UserView
from app.auth.passwords import generate_password
from app.auth.services import pwd_context
from app.projects.router import require_admin
from database.connection import DatabaseConnection
from database.models.base.user import User

router = APIRouter(prefix='', tags=['access'], dependencies=[Depends(require_admin)])


@router.get('/users', response_model=list[UserView])
async def list_users() -> list[User]:
    """List active accounts without password hashes."""
    async with DatabaseConnection() as conn:
        result = await conn.execute(
            select(User).where(User.deleted_at.is_(None)).order_by(User.name)
        )
        return list(result.scalars())


@router.post('/users', response_model=UserCreated, status_code=201)
async def create_user(body: UserInput, response: Response) -> UserCreated:
    """Create an account with a securely hashed initial password."""
    generated = generate_password() if body.password is None else None
    if generated:
        body = body.model_copy(update={'password': generated})
    user = await save_user(None, body)
    response.headers['Cache-Control'] = 'no-store'
    return UserCreated.model_validate(user).model_copy(
        update={'generated_password': generated}
    )


@router.put('/users/{user_id}', response_model=UserView)
async def update_user(user_id: int, body: UserInput) -> User:
    """Update identity, administrator status, or role assignment."""
    return await save_user(user_id, body)


async def save_user(user_id: int | None, body: UserInput) -> User:
    """Persist an account while preserving at least one administrator."""
    async with DatabaseConnection() as conn:
        # Serialize administrator changes so concurrent demotions cannot remove all admins.
        await conn.execute(text('LOCK TABLE base."user" IN SHARE ROW EXCLUSIVE MODE'))
        if body.role_id is not None:
            result = await conn.execute(
                text('SELECT id FROM base.role WHERE id = :id'),
                {'id': body.role_id},
            )
            role = result.scalar_one_or_none()
            if role is None:
                raise HTTPException(422, 'Role not found')
        user = await conn.get(User, user_id) if user_id is not None else User()
        if user is None or user.deleted_at is not None:
            raise HTTPException(404, 'User not found')
        if user_id and user.is_admin and not body.is_admin:
            await ensure_other_admin(conn, user_id)
        for key, value in body.model_dump(exclude={'password'}).items():
            setattr(user, key, value)
        user.email = str(body.email).lower()
        if body.password:
            user.password = pwd_context.hash(body.password)
        conn.add(user)
        try:
            await conn.commit()
            await conn.refresh(user)
        except IntegrityError:
            await conn.rollback()
            raise HTTPException(409, 'Email already exists')
        return user


async def ensure_other_admin(conn: AsyncSession, user_id: int) -> None:
    """Prevent removal of the last active administrator."""
    other = (await conn.execute(select(User.id).where(
        User.is_admin.is_(True), User.deleted_at.is_(None), User.id != user_id
    ))).first()
    if not other:
        raise HTTPException(409, 'At least one administrator must remain')


@router.delete('/users/{user_id}', status_code=204)
async def delete_user(user_id: int) -> Response:
    """Disable an account immediately while retaining audit references."""
    async with DatabaseConnection() as conn:
        await conn.execute(text('LOCK TABLE base."user" IN SHARE ROW EXCLUSIVE MODE'))
        user = await conn.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise HTTPException(404, 'User not found')
        if user.is_admin:
            await ensure_other_admin(conn, user_id)
        # Keep audit references and invalidate login, JWTs, and refresh tokens immediately.
        await conn.execute(
            text('UPDATE base."user" SET deleted_at = now(), role_id = NULL '
                 'WHERE id = :id'), {'id': user_id}
        )
        await conn.commit()
    return Response(status_code=204)
