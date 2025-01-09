from datetime import UTC, datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.models import ChannelType, Conversation, ConversationMember, User
from app.schemas import ChannelMemberInfo, ConversationInfo
from app.utils.access import verify_workspace_access
from app.utils.auth import get_current_user
from app.utils.db import get_db
from app.websocket import manager

router = APIRouter(prefix="/api/channels", tags=["channels"])


class ChannelMemberCreate(BaseModel):
    user_id: UUID
    is_admin: bool = False


class ChannelCreate(BaseModel):
    name: str
    description: str | None = None


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
        return [
            ChannelMemberInfo(
                user={
                    "id": str(user.id),
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar_url": user.avatar_url,
                    "is_online": user.is_online,
                },
                is_admin=member.is_admin,
                joined_at=member.joined_at,
            )
            for member, user in members
        ]


@router.post("", response_model=ConversationInfo)
async def create_channel(
    workspace_id: UUID,
    channel: ChannelCreate,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Create a new channel in a workspace."""
    with Session(engine) as session:
        # Verify workspace access
        verify_workspace_access(session, workspace_id, current_user.id)

        # Create the channel
        new_channel = Conversation(
            name=channel.name,
            description=channel.description,
            workspace_id=workspace_id,
            conversation_type=ChannelType.PUBLIC,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(new_channel)
        session.commit()
        session.refresh(new_channel)

        # Add creator to the channel
        channel_member = ConversationMember(
            conversation_id=new_channel.id,
            user_id=current_user.id,
            is_admin=True,
            joined_at=datetime.now(UTC),
        )
        session.add(channel_member)
        session.commit()

        return ConversationInfo.model_validate(new_channel.model_dump())
