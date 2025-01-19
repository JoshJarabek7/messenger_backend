from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlmodel import Session

from app.services.user_service import UserService
from tests.conftest import (
    TEST_USER_DISPLAY_NAME,
    TEST_USER_EMAIL,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient, db: Session):
    """Test user registration."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "newuser@example.com",
            "password": TEST_USER_PASSWORD,
            "username": "newuser",
            "display_name": "New User",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["username"] == "newuser"
    assert data["display_name"] == "New User"
    assert "id" in data
    assert UUID(data["id"])


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, db: Session):
    """Test registration with duplicate email."""
    # Create first user
    await client.post(
        "/api/auth/register",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "username": TEST_USER_USERNAME,
            "display_name": TEST_USER_DISPLAY_NAME,
        },
    )

    # Try to create second user with same email
    response = await client.post(
        "/api/auth/register",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "username": "different",
            "display_name": "Different User",
        },
    )
    assert response.status_code == 400
    assert "email already registered" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, db: Session):
    """Test successful login."""
    # Create user first
    user_service = UserService(db)
    user = user_service.create_user(
        email="logintest@example.com",
        password=TEST_USER_PASSWORD,
        username="logintest",
        display_name="Login Test User",
    )

    # Try to login
    response = await client.post(
        "/api/auth/login",
        json={
            "username": "logintest@example.com",
            "password": TEST_USER_PASSWORD,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # Verify cookies are set
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient, db: Session):
    """Test login with invalid credentials."""
    response = await client.post(
        "/api/auth/login",
        json={
            "username": TEST_USER_EMAIL,
            "password": "wrong_password",
        },
    )
    assert response.status_code == 401
    assert "invalid credentials" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, db: Session):
    """Test token refresh."""
    # Create user and get initial tokens
    user_service = UserService(db)
    user = user_service.create_user(
        email="refreshtest@example.com",
        password=TEST_USER_PASSWORD,
        username="refreshtest",
        display_name="Refresh Test User",
    )
    tokens = user_service.create_tokens(user.id)

    # Set the refresh token cookie
    client.cookies.set("refresh_token", tokens.refresh_token)

    # Try to refresh token
    response = await client.get("/api/auth/refresh-token")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_token_invalid(client: AsyncClient):
    """Test refresh token with invalid token."""
    # Set an invalid refresh token cookie
    client.cookies.set("refresh_token", "invalid_token")

    response = await client.get("/api/auth/refresh-token")
    assert response.status_code == 401
    assert "could not validate token" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_token_missing(client: AsyncClient):
    """Test refresh token endpoint with no token provided."""
    response = await client.get("/api/auth/refresh-token")
    assert response.status_code == 401
    assert "no refresh token provided" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    """Test logout endpoint."""
    response = await client.delete("/api/auth/logout")
    assert response.status_code == 200
    assert response.json()["message"] == "Successfully logged out"

    # Verify cookies are cleared
    assert "access_token" not in response.cookies
    assert "refresh_token" not in response.cookies
