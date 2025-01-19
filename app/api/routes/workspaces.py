from os import remove
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.domain import User, Workspace, WorkspaceMember
from app.services.workspace_service import WorkspaceService
from app.models.schemas.requests.workspace import (
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
    AddMemberRequest,
    UpdateMemberRoleRequest,
)
from app.models.schemas.responses.workspace import WorkspaceResponse

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("/", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Workspace]:
    """List all workspaces the user is a member of"""
    workspace_service = WorkspaceService(db)
    return workspace_service.get_user_workspaces(current_user.id)


@router.post("/", response_model=WorkspaceResponse)
async def create_workspace(
    workspace_data: CreateWorkspaceRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Workspace:
    """Create a new workspace"""
    workspace_service = WorkspaceService(db)
    result = workspace_service.create_workspace(
        name=workspace_data.name,
        description=workspace_data.description,
        created_by_id=current_user.id,
    )
    return result


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Workspace:
    """Get workspace by ID"""
    workspace_service = WorkspaceService(db)
    return workspace_service.get_workspace(workspace_id)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    workspace_data: UpdateWorkspaceRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Workspace:
    """Update workspace details"""
    workspace_service = WorkspaceService(db)
    return workspace_service.update_workspace(
        workspace_id=workspace_id,
        user_id=current_user.id,
        name=workspace_data.name,
        description=workspace_data.description,
    )


@router.delete("/{workspace_id}", response_model=None)
async def delete_workspace(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete workspace"""
    workspace_service = WorkspaceService(db)
    workspace_service.delete_workspace(
        workspace_id=workspace_id, user_id=current_user.id
    )
    return None


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMember])
async def list_workspace_members(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceMember]:
    """List all members of a workspace"""
    workspace_service = WorkspaceService(db)
    return workspace_service.get_members(workspace_id)


@router.post("/{workspace_id}/members", response_model=WorkspaceMember)
async def join_workspace(
    workspace_id: UUID,
    member_data: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceMember:
    """Join a workspace."""
    workspace_service = WorkspaceService(db)
    return workspace_service.add_member(
        workspace_id=workspace_id,
        user_id=member_data.user_id,
        role=member_data.role,
    )


@router.delete("/{workspace_id}/members/{user_id}", response_model=None)
async def remove_workspace_member(
    workspace_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """remove a member from the workspace"""
    workspace_service = WorkspaceService(db)
    workspace_service.remove_member(workspace_id=workspace_id, user_id=user_id)
    return None


@router.put("/{workspace_id}/members/{user_id}/role", response_model=WorkspaceMember)
async def update_member_role(
    workspace_id: UUID,
    user_id: UUID,
    role_data: UpdateMemberRoleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceMember:
    """Update a member's role in the workspace"""
    workspace_service = WorkspaceService(db)
    member = workspace_service.update_member_role(
        workspace_id=workspace_id,
        user_id=user_id,
        role=role_data.role,
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member
