from unittest.mock import patch
from typing import Optional, cast

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.models.domain import User
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_get_current_user_no_token(db: Session):
    """Test get_current_user with no token."""
    with pytest.raises(HTTPException) as exc:
        await get_current_user(access_token=cast(str, None), db=db)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Not authenticated"


@pytest.mark.asyncio
async def test_get_current_user_invalid_token(db: Session):
    """Test get_current_user with invalid token."""
    # Mock UserService to return None for invalid token
    with patch.object(UserService, "get_current_user", return_value=None):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(access_token="invalid_token", db=db)
        assert exc.value.status_code == 401
        assert exc.value.detail == "Invalid token"


@pytest.mark.asyncio
async def test_get_current_user_success(db: Session, test_user_in_db: User):
    """Test get_current_user with valid token."""
    # Mock UserService.get_current_user to return our test user
    with patch.object(
        UserService,
        "get_current_user",
        return_value=test_user_in_db,
    ):
        user = await get_current_user(access_token="valid_token", db=db)
        assert user.id == test_user_in_db.id
