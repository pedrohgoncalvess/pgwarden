import pytest
import pytest_asyncio

from httpx import AsyncClient
from passlib.context import CryptContext

from database.models.base import User


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@pytest_asyncio.fixture
async def test_user(db_session):
    """Creates a test user in the test database to ensure tests are independent."""
    user = User(
        email="test@example.com",
        password=pwd_context.hash("password123"),
        name="Test User",
        is_admin=True
    )
    db_session.add(user)
    await db_session.commit()
    return user

@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user):
    """Tests successful login using credentials created in the fixture."""
    login_data = {
        "email": "test@example.com",
        "password": "password123"
    }
    
    response = await client.post("/v1/auth", json=login_data)
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert "token" in data["access_token"]

@pytest.mark.asyncio
async def test_login_preflight_allows_vite_dev_origin(client: AsyncClient):
    """Tests that the Vite dev server can preflight login requests."""
    response = await client.options(
        "/v1/auth",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient, test_user):
    """Tests login failure when providing an incorrect password."""
    login_data = {
        "email": "test@example.com",
        "password": "wrongpassword"
    }
    
    response = await client.post("/v1/auth", json=login_data)
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Email or password incorrect."

@pytest.mark.asyncio
async def test_refresh_token_not_found(client: AsyncClient):
    """Tests the refresh endpoint with a token that does not exist in the database."""
    refresh_data = {
        "refresh_token": "00000000-0000-0000-0000-000000000000"
    }
    
    response = await client.post("/v1/auth/refresh", json=refresh_data)
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token."
