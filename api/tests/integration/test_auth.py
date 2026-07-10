import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user):
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
    login_data = {
        "email": "test@example.com",
        "password": "wrongpassword"
    }
    
    response = await client.post("/v1/auth", json=login_data)
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Email or password incorrect."

@pytest.mark.asyncio
async def test_refresh_token_not_found(client: AsyncClient):
    refresh_data = {
        "refresh_token": "00000000-0000-0000-0000-000000000000"
    }
    
    response = await client.post("/v1/auth/refresh", json=refresh_data)
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token."
