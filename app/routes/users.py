from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, or_, select

from app.models import User, WorkspaceMember
from app.utils.auth import get_current_user
from app.utils.db import get_session

router = APIRouter(prefix="/api/users", tags=["users"])


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
