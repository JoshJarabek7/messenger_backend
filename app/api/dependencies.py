from fastapi import Cookie, Depends, HTTPException
from sqlmodel import Session

from app.db.session import get_db
from app.models.domain import User
from app.services.user_service import UserService
from loguru import logger


# async def get_current_user(
#     access_token: str = Cookie(None), user_service: UserService = Depends()
# ) -> User:
#     """Get current user from access token."""
#     logger.info(f"Access token: {access_token}")
#     if not access_token:
#         raise HTTPException(status_code=401, detail="Not authenticated")

#     user = user_service.get_current_user(access_token)
#     if not user:
#         raise HTTPException(status_code=401, detail="Invalid token")

#     # Return the raw User model for authorization purposes
#     logger.info(f"Current user: {user}")
#     return user


async def get_current_user(
    access_token: str = Cookie(None), db: Session = Depends(get_db)
) -> User:
    """Get current user from access token."""
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_service = UserService(db)
    user = user_service.get_current_user(access_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    return user
