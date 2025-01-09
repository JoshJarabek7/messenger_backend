from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, or_, select

from app.models import User, WorkspaceMember
from app.storage import Storage
from app.utils.auth import get_current_user
from app.utils.db import get_session

router = APIRouter(prefix="/api/users", tags=["users"])


class UserUpdate(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None


@router.get("/search")
async def search_users(
    query: str = Query(..., min_length=1),
    workspace_id: Optional[UUID] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Search for users. If workspace_id is provided, only search within that workspace.
    """
    user_query = select(User).where(
        or_(
            User.username.ilike(f"%{query}%"),
            User.display_name.ilike(f"%{query}%"),
            User.email.ilike(f"%{query}%"),
        )
    )

    if workspace_id:
        user_query = user_query.join(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id
        )

    users = session.exec(user_query).all()
    return [
        {
            "id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "email": user.email if workspace_id else None,
        }
        for user in users
    ]


@router.get("/username-exists/{username}")
async def check_username_exists(
    username: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Check if a username is already taken."""
    user = session.exec(
        select(User).where(User.username == username, User.id != current_user.id)
    ).first()
    return {"exists": user is not None}


@router.put("/me")
async def update_user_profile(
    user_update: UserUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update the current user's profile."""
    # Check if username is taken
    if user_update.username and user_update.username != current_user.username:
        existing_user = session.exec(
            select(User).where(
                User.username == user_update.username, User.id != current_user.id
            )
        ).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already taken")

    if user_update.avatar_url:
        print(f"User update avatar url: {user_update.avatar_url}")
        print("ENSURE THE ABOVE IS THE FILE ID AND NOT THE DOWNLOAD URL")
        # Extract UUID from S3 URL
        parsed_url = urlparse(user_update.avatar_url)
        # Get the path without leading slash and split on query params
        s3_key = parsed_url.path.lstrip("/").split("?")[0]
        user_update.avatar_url = s3_key  # Replace URL with just the S3 key
        print(f"PARSED S3 KEY AND URL: {s3_key}")

    # Update user fields
    if user_update.username is not None:
        current_user.username = user_update.username
    if user_update.display_name is not None:
        current_user.display_name = user_update.display_name
    if user_update.email is not None:
        current_user.email = user_update.email
    if user_update.avatar_url is not None:
        current_user.avatar_url = user_update.avatar_url

    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    storage = Storage()
    avatar_url = storage.create_presigned_url(current_user.avatar_url)

    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "display_name": current_user.display_name,
        "email": current_user.email,
        "avatar_url": avatar_url,
    }
