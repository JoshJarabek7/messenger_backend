from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, or_
from typing import List, Optional
from uuid import UUID

from app.db import get_session
from app.models import User, Workspace, WorkspaceMember
from app.auth_utils import get_current_user

router = APIRouter(prefix="/api/search", tags=["search"])

@router.get("/global")
async def search_global(
    query: str = Query(..., min_length=1),
    workspace_id: Optional[UUID] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Search for users and workspaces globally.
    If workspace_id is provided, only search within that workspace's context.
    """
    results = {
        "users": [],
        "workspaces": []
    }

    # Search for users
    user_query = select(User).where(
        or_(
            User.username.ilike(f"%{query}%"),
            User.display_name.ilike(f"%{query}%"),
            User.email.ilike(f"%{query}%")
        )
    )

    if workspace_id:
        user_query = user_query.join(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)

    users = session.exec(user_query).all()
    results["users"] = [
        {
            "id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "email": user.email if workspace_id else None
        }
        for user in users
    ]

    # Search for workspaces
    # Only search workspaces the user is a member of
    workspace_query = select(Workspace).where(
        Workspace.name.ilike(f"%{query}%")
    ).join(WorkspaceMember).where(WorkspaceMember.user_id == current_user.id)

    workspaces = session.exec(workspace_query).all()
    results["workspaces"] = [
        {
            "id": str(workspace.id),
            "name": workspace.name,
            "icon_url": workspace.icon_url,
            "slug": workspace.slug
        }
        for workspace in workspaces
    ]

    return results 