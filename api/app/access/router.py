"""Register administrator-managed identity endpoints."""
from fastapi import APIRouter
from app.access.roles import router as roles_router
from app.access.users import router as users_router

router = APIRouter(prefix='/access')
router.include_router(roles_router)
router.include_router(users_router)
