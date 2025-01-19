from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from app.core.config import get_settings
from app.models.domain import User
from app.services.user_service import UserService
from app.exceptions.user_exceptions import UserNotFoundError


@pytest.fixture
def user_service(db: Session):
    return UserService(db)


@pytest.fixture
def test_user_data() -> dict:
    return {
        "email": "test@example.com",
        "username": "testuser",
        "password": "testpassword123",
        "display_name": "Test User",
    }


@pytest.mark.asyncio
async def test_create_user_success(user_service: UserService, test_user_data: dict):
    user = user_service.create_user(**test_user_data)
    assert user.email == test_user_data["email"]
    assert user.username == test_user_data["username"]
    assert user.display_name == test_user_data["display_name"]
    assert (
        user.hashed_password != test_user_data["password"]
    )  # Password should be hashed


@pytest.mark.asyncio
async def test_create_user_duplicate_email(
    user_service: UserService, test_user_data: dict
):
    # Create first user
    user_service.create_user(**test_user_data)

    # Try to create another user with same email
    with pytest.raises(HTTPException) as exc_info:
        user_service.create_user(**test_user_data)
    assert exc_info.value.status_code == 400
    assert "Email already registered" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_create_user_duplicate_username(
    user_service: UserService, test_user_data: dict
):
    # Create first user
    user_service.create_user(**test_user_data)

    # Try to create another user with same username but different email
    new_data = test_user_data.copy()
    new_data["email"] = "another@example.com"
    with pytest.raises(HTTPException) as exc_info:
        user_service.create_user(**new_data)
    assert exc_info.value.status_code == 400
    assert "Username already taken" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_authenticate_user_success(
    user_service: UserService, test_user_data: dict
):
    # Create a user first
    user_service.create_user(**test_user_data)

    # Try to authenticate
    user = user_service.authenticate_user(
        test_user_data["email"], test_user_data["password"]
    )
    assert user is not None
    assert user.email == test_user_data["email"]


@pytest.mark.asyncio
async def test_authenticate_user_invalid_email(user_service: UserService):
    with pytest.raises(HTTPException) as exc_info:
        user_service.authenticate_user("nonexistent@example.com", "password123")
    assert exc_info.value.status_code == 401
    assert "Invalid credentials" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_authenticate_user_invalid_password(
    user_service: UserService, test_user_data: dict
):
    # Create a user first
    user_service.create_user(**test_user_data)

    # Try to authenticate with wrong password
    with pytest.raises(HTTPException) as exc_info:
        user_service.authenticate_user(test_user_data["email"], "wrongpassword")
    assert exc_info.value.status_code == 401
    assert "Invalid credentials" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_create_access_token(user_service: UserService, test_user_in_db: User):
    token = user_service.create_access_token(test_user_in_db.id)
    assert isinstance(token, str)
    assert len(token) > 0


@pytest.mark.asyncio
async def test_create_refresh_token(user_service: UserService, test_user_in_db: User):
    token = user_service.create_refresh_token(test_user_in_db.id)
    assert isinstance(token, str)
    assert len(token) > 0


@pytest.mark.asyncio
async def test_verify_token_success(user_service: UserService, test_user_in_db: User):
    token = user_service.create_access_token(test_user_in_db.id)
    token_data = user_service.verify_token(token, "access")
    assert token_data.user_id == test_user_in_db.id


@pytest.mark.asyncio
async def test_verify_token_expired(user_service: UserService, test_user_in_db: User):
    # Create a token that's already expired
    expired_delta = timedelta(minutes=-1)  # Token expired 1 minute ago
    token = user_service.create_access_token(
        test_user_in_db.id, expires_delta=expired_delta
    )

    with pytest.raises(HTTPException) as exc_info:
        user_service.verify_token(token, "access")
    assert exc_info.value.status_code == 401
    assert "Could not validate token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_verify_token_invalid(user_service: UserService):
    with pytest.raises(HTTPException) as exc_info:
        user_service.verify_token("invalid.token.here", "access")
    assert exc_info.value.status_code == 401
    assert "Could not validate token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_current_user_success(
    user_service: UserService, test_user_data: dict
):
    # Create and store the user
    stored_user = user_service.create_user(**test_user_data)

    # Create a token for the user
    token = user_service.create_access_token(stored_user.id)

    # Get current user using the token
    current_user = user_service.get_current_user(token)
    assert current_user is not None
    assert current_user.id == stored_user.id
    assert current_user.email == stored_user.email


@pytest.mark.asyncio
async def test_get_current_user_invalid_token(user_service: UserService):
    with pytest.raises(HTTPException) as exc_info:
        user_service.get_current_user("invalid.token.here")
    assert exc_info.value.status_code == 401
    assert "Could not validate token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_current_user_user_not_found(
    user_service: UserService, test_user_in_db: User
):
    # Create a token for a user that doesn't exist in the database
    token = user_service.create_access_token(test_user_in_db.id)

    # Delete the user from the database
    user_service.db.delete(test_user_in_db)
    user_service.db.commit()

    with pytest.raises(UserNotFoundError) as exc_info:
        user_service.get_current_user(token)
    assert "User not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_user_by_id_success(user_service: UserService, test_user_data: dict):
    # Create a user
    user = user_service.create_user(**test_user_data)

    # Get user by ID
    retrieved_user = user_service.get_user_by_id(user.id)
    assert retrieved_user is not None
    assert retrieved_user.id == user.id
    assert retrieved_user.email == user.email


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(
    user_service: UserService, test_user_in_db: User
):
    # Delete the user from the database
    user_service.db.delete(test_user_in_db)
    user_service.db.commit()

    with pytest.raises(HTTPException) as exc_info:
        user_service.get_user_by_id(test_user_in_db.id)
    assert exc_info.value.status_code == 404
    assert "User not found" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_user_by_email_success(
    user_service: UserService, test_user_data: dict
):
    # Create a user
    user = user_service.create_user(**test_user_data)

    # Get user by email
    retrieved_user = user_service.get_user_by_email(user.email)
    assert retrieved_user is not None
    assert retrieved_user.id == user.id
    assert retrieved_user.email == user.email


@pytest.mark.asyncio
async def test_get_user_by_email_not_found(user_service: UserService):
    with pytest.raises(HTTPException) as exc_info:
        user_service.get_user_by_email("nonexistent@example.com")
    assert exc_info.value.status_code == 404
    assert "User not found" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_user_by_username_success(
    user_service: UserService, test_user_data: dict
):
    # Create a user
    user = user_service.create_user(**test_user_data)

    # Get user by username
    retrieved_user = user_service.get_user_by_username(user.username)
    assert retrieved_user is not None
    assert retrieved_user.id == user.id
    assert retrieved_user.username == user.username


@pytest.mark.asyncio
async def test_get_user_by_username_not_found(user_service: UserService):
    with pytest.raises(HTTPException) as exc_info:
        user_service.get_user_by_username("nonexistent_user")
    assert exc_info.value.status_code == 404
    assert "User not found" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_update_user_success(user_service: UserService, test_user_data):
    # Create a user
    user = user_service.create_user(**test_user_data)

    # Update user
    new_display_name = "Updated Name"
    updated_user = user_service.update_user(user.id, display_name=new_display_name)

    assert updated_user.display_name == new_display_name
    assert updated_user.id == user.id
    assert updated_user.email == user.email  # Other fields should remain unchanged


@pytest.mark.asyncio
async def test_update_user_not_found(user_service: UserService):
    """Test updating a user that doesn't exist."""
    non_existent_id = uuid4()
    with pytest.raises(UserNotFoundError):
        user_service.update_user(
            user_id=non_existent_id,
            display_name="New Name",
            username="newusername",
        )
