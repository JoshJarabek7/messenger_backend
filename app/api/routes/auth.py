from fastapi import APIRouter, Depends, Response, Cookie, HTTPException

from loguru import logger

from app.api.dependencies import get_current_user
from app.models.domain import User
from app.models.schemas.requests.user import UserCreateRequest
from app.models.schemas.responses.token import Token
from app.models.schemas.responses.user import UserResponse
from app.services.user_service import UserService
from sqlmodel import Session
from app.db.session import get_db
from app.core.config import get_settings
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register", response_model=UserResponse)
async def register(
    response: Response, user_data: UserCreateRequest, db: Session = Depends(get_db)
) -> UserResponse:
    """Register a new user."""
    user_service = UserService(db)
    user = user_service.create_user(**user_data.model_dump())
    tokens = user_service.create_tokens(user.id)
    # Set cookies with proper expiration from settings
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
        httponly=True,
        secure=False,
        samesite="lax",
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=False,
        samesite="lax",
    )

    return UserResponse.model_validate(user)


@router.post("/login", response_model=None)
async def login(
    response: Response,
    login_request: LoginRequest,
    db: Session = Depends(get_db),
) -> None:
    """Login user."""
    logger.info(f"Login request: {login_request}")

    user_service = UserService(db)

    user = user_service.authenticate_user(
        login_request.username, login_request.password
    )
    tokens = user_service.create_tokens(user.id)

    # Set cookies with proper expiration from settings
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
        httponly=True,
        secure=False,
        samesite="lax",
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=False,
        samesite="lax",
    )

    return None


@router.get("/refresh-token", response_model=None)
async def refresh_token(
    response: Response,
    refresh_token: str | None = Cookie(None),
    db: Session = Depends(get_db),
) -> None:
    """Refresh access token."""
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token provided")

    user_service = UserService(db)
    tokens = user_service.refresh_tokens(refresh_token)

    # Set new cookies with proper expiration from settings
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
        httponly=True,
        secure=False,
        samesite="lax",
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
        httponly=True,
        secure=False,
        samesite="lax",
    )

    return None


@router.delete("/logout", response_model=None)
async def logout(response: Response, _: User = Depends(get_current_user)) -> None:
    """Logout user by clearing cookies"""
    response.delete_cookie(
        key="access_token", secure=True, httponly=True, samesite="lax"
    )
    response.delete_cookie(
        key="refresh_token", secure=True, httponly=True, samesite="lax"
    )
    return None


@router.get("/verify-token", response_model=UserResponse)
async def verify_token(user: User = Depends(get_current_user)) -> UserResponse:
    """Verify user token"""
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        display_name=user.display_name,
        is_online=user.is_online,
        s3_key=user.s3_key,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
