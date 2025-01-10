from datetime import UTC, datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.models import (
    ChannelType,
    Conversation,
    ConversationMember,
    FileAttachment,
    Message,
    User,
    WorkspaceMember,
)
from app.schemas import ChannelMemberInfo, ConversationInfo
from app.storage import Storage
from app.utils.access import verify_workspace_access
from app.utils.auth import get_current_user
from app.utils.db import get_db
from app.websocket import WebSocketMessageType, manager

router = APIRouter(prefix="/api/channels", tags=["channels"])

# Initialize storage
storage = Storage()


class ChannelMemberCreate(BaseModel):
    user_id: UUID
    is_admin: bool = False


class ChannelCreate(BaseModel):
    name: str
    description: str | None = None
    workspace_id: UUID


def verify_conversation_access(
    session: Session, conversation_id: UUID, user_id: UUID, require_admin: bool = False
) -> Conversation:
    """Verify user has access to a conversation and optionally check if they're an admin."""
    conversation = session.exec(
        select(Conversation).where(Conversation.id == conversation_id)
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    member = session.exec(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id,
        )
    ).first()

    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this conversation")

    if require_admin and not member.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    return conversation


@router.post("/{channel_id}/members")
async def add_channel_member(
    channel_id: UUID,
    member: ChannelMemberCreate,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Add a member to a channel."""
    with Session(engine) as session:
        # Verify access and get channel
        verify_conversation_access(
            session, channel_id, current_user.id, require_admin=True
        )

        # Check if user is already a member
        existing_member = session.exec(
            select(ConversationMember).where(
                ConversationMember.conversation_id == channel_id,
                ConversationMember.user_id == member.user_id,
            )
        ).first()

        if existing_member:
            raise HTTPException(
                status_code=400, detail="User is already a member of this channel"
            )

        # Add new member
        new_member = ConversationMember(
            conversation_id=channel_id, user_id=member.user_id, is_admin=member.is_admin
        )
        session.add(new_member)
        session.commit()

        # Subscribe new member to channel
        manager.subscribe_to_channel(member.user_id, channel_id)

        return {"status": "success"}


@router.delete("/{channel_id}/members/{user_id}")
async def remove_channel_member(
    channel_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Remove a member from a channel."""
    with Session(engine) as session:
        # Allow self-removal or require admin access
        require_admin = user_id != current_user.id
        verify_conversation_access(
            session, channel_id, current_user.id, require_admin=require_admin
        )

        # Remove member
        member = session.exec(
            select(ConversationMember).where(
                ConversationMember.conversation_id == channel_id,
                ConversationMember.user_id == user_id,
            )
        ).first()

        if member:
            session.delete(member)
            session.commit()

            # Unsubscribe user from channel
            manager.unsubscribe_from_channel(user_id, channel_id)

        return {"status": "success"}


@router.get("/{channel_id}/members", response_model=List[ChannelMemberInfo])
async def get_channel_members(
    channel_id: UUID,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get all members of a channel."""
    with Session(engine) as session:
        # Verify access to channel
        verify_conversation_access(session, channel_id, current_user.id)

        # Get all members with user info
        members = session.exec(
            select(ConversationMember, User)
            .join(User, ConversationMember.user_id == User.id)
            .where(ConversationMember.conversation_id == channel_id)
        ).all()

        # Convert to response model
        members_data = []
        for member, user in members:
            members_data.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar_url": user.avatar_url,
                    "is_online": manager.is_user_online(user.id),
                }
            )

        return members_data


@router.post("", response_model=ConversationInfo)
async def create_channel(
    channel: ChannelCreate,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Create a new channel in a workspace."""
    with Session(engine) as session:
        # Verify workspace access
        verify_workspace_access(session, channel.workspace_id, current_user.id)

        # Check if channel name already exists in this workspace
        existing_channel = session.exec(
            select(Conversation).where(
                Conversation.workspace_id == channel.workspace_id,
                Conversation.name == channel.name,
                Conversation.conversation_type == ChannelType.PUBLIC,
            )
        ).first()

        if existing_channel:
            raise HTTPException(
                status_code=400,
                detail="A channel with this name already exists in this workspace",
            )

        # Create the channel
        new_channel = Conversation(
            name=channel.name,
            description=channel.description,
            workspace_id=channel.workspace_id,
            conversation_type=ChannelType.PUBLIC,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(new_channel)
        session.commit()
        session.refresh(new_channel)

        # Get all workspace members
        workspace_members = session.exec(
            select(User)
            .join(User.workspaces)
            .where(User.workspaces.any(id=channel.workspace_id))
        ).all()

        # Add all workspace members to the channel
        for member in workspace_members:
            channel_member = ConversationMember(
                conversation_id=new_channel.id,
                user_id=member.id,
                # Make the creator an admin
                is_admin=member.id == current_user.id,
                joined_at=datetime.now(UTC),
            )
            session.add(channel_member)
        session.commit()

        # Convert to response model
        channel_info = ConversationInfo(
            id=str(new_channel.id),
            name=new_channel.name,
            description=new_channel.description,
            conversation_type=ChannelType.PUBLIC,
            workspace_id=str(new_channel.workspace_id),
            created_at=new_channel.created_at,
            updated_at=new_channel.updated_at,
        )

        # Send WebSocket notification to all workspace members
        await manager.broadcast_to_workspace(
            channel.workspace_id,
            WebSocketMessageType.CHANNEL_CREATED,
            channel_info.model_dump(),
        )

        return channel_info


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a channel and all its messages and files."""
    print(f"\n=== Deleting Channel {channel_id} ===")
    print(f"Requested by user: {current_user.id}")

    with Session(db) as session:
        # Get the channel (which is a conversation)
        channel = session.get(Conversation, channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        # Verify this is actually a channel
        if channel.conversation_type not in [ChannelType.PUBLIC, ChannelType.PRIVATE]:
            raise HTTPException(status_code=400, detail="This is not a channel")

        # Get the workspace members to check permissions
        workspace_member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == channel.workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        ).first()

        if not workspace_member or workspace_member.role not in ["admin", "owner"]:
            raise HTTPException(
                status_code=403,
                detail="Only workspace admins and owners can delete channels",
            )

        # Get all workspace members for notification BEFORE deletion
        workspace_members = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == channel.workspace_id
            )
        ).all()
        member_ids = [member.user_id for member in workspace_members]

        # Store channel info for notification
        channel_info = {
            "id": str(channel_id),
            "workspace_id": str(channel.workspace_id),
            "name": channel.name,
        }

        # Get all messages with their file attachments
        messages = session.exec(
            select(Message).where(Message.conversation_id == channel.id)
        ).all()

        # Delete all file attachments from S3 and database
        for message in messages:
            file_attachments = session.exec(
                select(FileAttachment).where(FileAttachment.message_id == message.id)
            ).all()

            for attachment in file_attachments:
                # Delete from S3
                try:
                    storage.delete_file(attachment.s3_key)
                except Exception as e:
                    print(f"Error deleting file {attachment.s3_key} from S3: {e}")

                # Delete from database
                session.delete(attachment)

            # Delete the message
            session.delete(message)

        # Delete the channel (conversation)
        session.delete(channel)
        session.commit()

        print(f"Successfully deleted channel {channel_id}")

        # Send WebSocket notification about channel deletion to all workspace members
        await manager.broadcast_to_users(
            member_ids,
            WebSocketMessageType.CHANNEL_DELETED,
            channel_info,
        )

        return {"status": "success", "message": "Channel deleted successfully"}
