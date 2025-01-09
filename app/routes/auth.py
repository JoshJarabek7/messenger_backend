from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr

from app.managers.user_manager import user_manager
from app.models import User
from app.utils.auth import auth_utils, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    display_name: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    display_name: Optional[str]
    avatar_url: Optional[str]


@router.post("/register")
async def register(user_data: UserCreate, response: Response):
    try:
        print(f"Attempting to register user with email: {user_data.email}")
        # Create user
        user = user_manager.create_user(
            email=user_data.email,
            username=user_data.username,
            password=user_data.password,
            display_name=user_data.display_name,
        )

        # Generate tokens
        tokens = auth_utils.create_tokens(user.id)

        # Set both tokens as HTTP-only cookies
        response.set_cookie(
            key="access_token",
            value=tokens.access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=30 * 60,  # 30 minutes
        )

        response.set_cookie(
            key="refresh_token",
            value=tokens.refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,  # 7 days
        )

        return {
            "user": UserResponse(
                id=str(user.id),
                email=user.email,
                username=user.username,
                display_name=user.display_name,
                avatar_url=user.avatar_url,
            )
        }
    except Exception as e:
        print(f"Registration error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login")
async def login(user_data: UserLogin, response: Response):
    # Authenticate user
    user = user_manager.authenticate_user(user_data.email, user_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    # Generate tokens
    tokens = auth_utils.create_tokens(user.id)

    # Set both tokens as HTTP-only cookies
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=30 * 60,  # 30 minutes
    )

    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7 days
    )

    return {
        "user": UserResponse(
            id=str(user.id),
            email=user.email,
            username=user.username,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
        )
    }


@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    """Refresh access token using refresh token from cookies"""
    refresh_token = request.cookies.get("refresh_token")
    print("Refresh token from cookie:", refresh_token)

    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token provided")

    try:
        # Generate new tokens
        tokens = auth_utils.refresh_tokens(refresh_token)

        # Set both tokens as HTTP-only cookies
        response.set_cookie(
            key="access_token",
            value=tokens.access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=30 * 60,  # 30 minutes
        )

        response.set_cookie(
            key="refresh_token",
            value=tokens.refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,  # 7 days
        )

        return {"message": "Tokens refreshed successfully"}
    except Exception as e:
        print("Refresh token error:", str(e))
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.get("/verify")
async def verify_token(request: Request, user: User = Depends(get_current_user)):
    """Verify access token and return user data"""
    print("Verify endpoint - Cookies received:", request.cookies)
    print("Access token from cookie:", request.cookies.get("access_token"))
    return UserResponse(
        id=str(user.id),
        email=user.email,
        username=user.username,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
    )


@router.post("/logout")
async def logout(response: Response):
    """Clear both token cookies"""
    response.delete_cookie(
        key="access_token", secure=True, httponly=True, samesite="lax"
    )
    response.delete_cookie(
        key="refresh_token", secure=True, httponly=True, samesite="lax"
    )
    return {"message": "Successfully logged out"}
