from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from sqlalchemy import Engine
from typing import List
from uuid import UUID
from pydantic import BaseModel

from app.utils.db import get_db
from app.models import User, ChannelMember
from app.utils.auth import get_current_user
from app.websocket import manager
from app.schemas import ChannelMemberInfo
from app.utils.access import verify_conversation_access

router = APIRouter(prefix="/api/channels", tags=["channels"])

class ChannelMemberCreate(BaseModel):
    user_id: UUID
    is_admin: bool = False

@router.post("/{channel_id}/members")
async def add_channel_member(
    channel_id: UUID,
    member: ChannelMemberCreate,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db)
):
    """Add a member to a channel."""
    with Session(engine) as session:
        # Verify access and get channel
        conversation = verify_conversation_access(session, channel_id, current_user.id, require_admin=True)
        
        # Check if user is already a member
        existing_member = session.exec(
            select(ChannelMember).where(
                ChannelMember.channel_id == channel_id,
                ChannelMember.user_id == member.user_id
            )
        ).first()
        
        if existing_member:
            raise HTTPException(status_code=400, detail="User is already a member of this channel")
        
        # Add new member
        new_member = ChannelMember(
            channel_id=channel_id,
            user_id=member.user_id,
            is_admin=member.is_admin
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
    engine: Engine = Depends(get_db)
):
    """Remove a member from a channel."""
    with Session(engine) as session:
        # Allow self-removal or require admin access
        require_admin = user_id != current_user.id
        conversation = verify_conversation_access(session, channel_id, current_user.id, require_admin=require_admin)
        
        # Remove member
        member = session.exec(
            select(ChannelMember).where(
                ChannelMember.channel_id == channel_id,
                ChannelMember.user_id == user_id
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
    engine: Engine = Depends(get_db)
):
    """Get all members of a channel."""
    with Session(engine) as session:
        # Verify access to channel
        conversation = verify_conversation_access(session, channel_id, current_user.id)
        
        # Get all members with user info
        members = session.exec(
            select(ChannelMember, User)
            .join(User, ChannelMember.user_id == User.id)
            .where(ChannelMember.channel_id == channel_id)
        ).all()
        
        # Convert to response model
        return [
            ChannelMemberInfo(
                user={
                    "id": str(user.id),
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar_url": user.avatar_url,
                    "is_online": user.is_online
                },
                is_admin=member.is_admin,
                joined_at=member.joined_at
            )
            for member, user in members
        ] 