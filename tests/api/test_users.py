from uuid import UUID

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlmodel import Session

from app.models.domain import User
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, test_user_in_db: User):
    """Test getting current user."""
    response = await client.get("/api/users/me")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_user_in_db.id)
    assert data["email"] == test_user_in_db.email
    assert data["username"] == test_user_in_db.username
    assert data["display_name"] == test_user_in_db.display_name


@pytest.mark.asyncio
async def test_get_user(client: AsyncClient, test_user_in_db: User):
    """Test getting a specific user."""
    response = await client.get(f"/api/users/{test_user_in_db.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_user_in_db.id)
    assert data["email"] == test_user_in_db.email
    assert data["username"] == test_user_in_db.username
    assert data["display_name"] == test_user_in_db.display_name


@pytest.mark.asyncio
async def test_get_user_not_found(client: AsyncClient):
    """Test getting a non-existent user."""
    response = await client.get(f"/api/users/{UUID(int=0)}")
    assert response.status_code == 404
    assert "user not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_me(client: AsyncClient, test_user_in_db: User):
    """Test updating current user."""
    response = await client.put(
        "/api/users/me",
        json={
            "email": "updated@example.com",
            "username": "updated_user",
            "display_name": "Updated User",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "updated@example.com"
    assert data["username"] == "updated_user"
    assert data["display_name"] == "Updated User"


@pytest.mark.asyncio
async def test_update_me_duplicate_email(
    client: AsyncClient, test_user_in_db: User, test_other_user_in_db: User
):
    """Test updating current user with an email that's already taken."""
    response = await client.put(
        "/api/users/me",
        json={
            "email": test_other_user_in_db.email,
            "username": "new_username",
            "display_name": "New Name",
        },
    )
    assert response.status_code == 400
    assert "email already registered" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_me_duplicate_username(
    client: AsyncClient, test_user_in_db: User, test_other_user_in_db: User
):
    """Test updating current user with a username that's already taken."""
    response = await client.put(
        "/api/users/me",
        json={
            "email": "new@example.com",
            "username": test_other_user_in_db.username,
            "display_name": "New Name",
        },
    )
    assert response.status_code == 400
    assert "username already taken" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_me(client: AsyncClient, test_user_in_db: User, db: Session):
    """Test deleting current user."""
    # Delete user
    response = await client.delete("/api/users/me")
    assert response.status_code == 200
    assert response.json()["message"] == "User deleted successfully"

    # Try to get deleted user - should fail
    user_service = UserService(db)
    with pytest.raises(HTTPException) as exc_info:
        user_service.get_user_by_id(test_user_in_db.id)
    assert exc_info.value.status_code == 404
    assert "User not found" in str(exc_info.value.detail)
