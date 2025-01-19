from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_current_user
from app.models.domain import Message, User
from app.models.schemas.requests.channel import (
    CreateChannelMessageRequest,
    CreateChannelRequest,
    UpdateChannelRequest,
)
from app.models.schemas.responses.channel import ChannelResponse
from app.models.schemas.responses.message import MessageResponse
from app.services.channel_service import ChannelService

from app.services.workspace_permission_service import WorkspacePermissionService
from app.services.workspace_service import WorkspaceService
from app.models.domain import WorkspaceRole
from sqlmodel import Session
from app.db.session import get_db

router = APIRouter(prefix="/api/workspaces", tags=["channels"])


@router.get("/{workspace_id}/channels", response_model=list[ChannelResponse])
async def list_channels(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ChannelResponse]:
    """List all channels in a workspace."""
    workspace_service = WorkspaceService(db)
    # Check if workspace exists
    workspace = workspace_service.get_workspace(workspace_id)

    permission_service = WorkspacePermissionService(db)
    if not permission_service.check_permission(
        current_user.id,
        workspace_id,
        [WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER],
    ):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view channels in this workspace",
        )

    channels = workspace_service.get_channels(workspace_id)
    return [ChannelResponse.model_validate(channel) for channel in channels]


@router.post("/{workspace_id}/channels", response_model=ChannelResponse)
async def create_channel(
    workspace_id: UUID,
    channel_data: CreateChannelRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ChannelResponse:
    """Create a new channel in a workspace."""
    workspace_service = WorkspaceService(db)
    # Check if workspace exists
    workspace = workspace_service.get_workspace(workspace_id)

    permission_service = WorkspacePermissionService(db)
    if not permission_service.can_manage_channels(current_user.id, workspace_id):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to create channels in this workspace",
        )

    channel = workspace_service.create_channel(
        workspace_id=workspace_id,
        name=channel_data.name,
        description=channel_data.description,
        created_by_id=current_user.id,
    )
    return ChannelResponse.model_validate(channel)


@router.get("/{workspace_id}/channels/{channel_slug}", response_model=ChannelResponse)
async def get_channel(
    workspace_id: UUID,
    channel_slug: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ChannelResponse:
    """Get a channel by slug."""
    workspace_service = WorkspaceService(db)
    # Check if workspace exists
    workspace = workspace_service.get_workspace(workspace_id)

    channel = workspace_service.get_channel(workspace_id, channel_slug)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    permission_service = WorkspacePermissionService(db)
    if not permission_service.can_view_channel(current_user.id, channel.id):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view this channel",
        )

    return ChannelResponse.model_validate(channel)


@router.put("/{workspace_id}/channels/{channel_slug}", response_model=ChannelResponse)
async def update_channel(
    workspace_id: UUID,
    channel_slug: str,
    channel_data: UpdateChannelRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ChannelResponse:
    """Update a channel."""
    workspace_service = WorkspaceService(db)
    # Check if workspace exists
    workspace = workspace_service.get_workspace(workspace_id)

    channel = workspace_service.get_channel(workspace_id, channel_slug)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    permission_service = WorkspacePermissionService(db)
    if not permission_service.can_manage_channels(current_user.id, workspace_id):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to update channels in this workspace",
        )

    channel_service = ChannelService(db)
    updated_channel = channel_service.update(
        channel_id=channel.id,
        name=channel_data.name,
        description=channel_data.description,
    )
    if not updated_channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ChannelResponse.model_validate(updated_channel)


@router.delete("/{workspace_id}/channels/{channel_slug}", response_model=dict[str, str])
async def delete_channel(
    workspace_id: UUID,
    channel_slug: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Delete a channel."""
    workspace_service = WorkspaceService(db)
    # Check if workspace exists
    workspace = workspace_service.get_workspace(workspace_id)

    channel = workspace_service.get_channel(workspace_id, channel_slug)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    permission_service = WorkspacePermissionService(db)
    if not permission_service.can_manage_channels(current_user.id, workspace_id):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to delete channels in this workspace",
        )

    channel_service = ChannelService(db)
    channel_service.delete(channel.id)
    return {"message": "Channel deleted successfully"}


@router.get(
    "/{workspace_id}/channels/{channel_slug}/messages",
    response_model=list[MessageResponse],
)
async def list_channel_messages(
    workspace_id: UUID,
    channel_slug: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 50,
    before_message_id: UUID | None = None,
) -> list[MessageResponse]:
    """List messages in a channel."""
    workspace_service = WorkspaceService(db)
    # Check if workspace exists
    workspace = workspace_service.get_workspace(workspace_id)

    channel = workspace_service.get_channel(workspace_id, channel_slug)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    permission_service = WorkspacePermissionService(db)
    if not permission_service.can_view_channel(current_user.id, channel.id):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view messages in this channel",
        )

    channel_service = ChannelService(db)
    messages = channel_service.get_messages(
        channel_id=channel.id,
        limit=limit,
        before_message_id=before_message_id,
    )
    return [MessageResponse.model_validate(msg) for msg in messages]


@router.post(
    "/{workspace_id}/channels/{channel_slug}/messages", response_model=MessageResponse
)
async def create_channel_message(
    workspace_id: UUID,
    channel_slug: str,
    message_data: CreateChannelMessageRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    """Create a new message in a channel."""
    workspace_service = WorkspaceService(db)
    # Check if workspace exists
    workspace = workspace_service.get_workspace(workspace_id)

    channel = workspace_service.get_channel(workspace_id, channel_slug)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    permission_service = WorkspacePermissionService(db)
    if not permission_service.can_view_channel(current_user.id, channel.id):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to send messages in this channel",
        )

    channel_service = ChannelService(db)
    message = Message(
        content=message_data.content,
        user_id=current_user.id,
        channel_id=channel.id,
        parent_id=message_data.parent_id,
    )
    created_message = channel_service.create_message(
        channel_id=channel.id, message=message
    )
    return MessageResponse.model_validate(created_message)
