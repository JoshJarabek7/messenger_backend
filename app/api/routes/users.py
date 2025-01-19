from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.domain import User
from app.models.schemas.requests.user import UserUpdateRequest
from app.models.schemas.responses.user import UserResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Get current user."""
    return UserResponse.model_validate(current_user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
) -> UserResponse:
    """Get a user by ID."""
    user_service = UserService(db)
    user = user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)


@router.put("/me", response_model=UserResponse)
async def update_me(
    user_data: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Update current user."""
    user_service = UserService(db)
    updated_user = user_service.update_user(current_user.id, **user_data.model_dump())
    return UserResponse.model_validate(updated_user)


@router.delete("/me", response_model=None)
async def delete_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete current user."""
    user_service = UserService(db)
    user_service.delete_user(current_user.id)
    return None
