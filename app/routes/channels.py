from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy import Engine
from typing import List
from uuid import UUID
from datetime import datetime, UTC

from app.db import get_db
from app.models import Channel, Message, User, ChannelMember, ChannelType
from app.auth_utils import get_current_user
from app.websocket_manager import manager, WebSocketMessageType

router = APIRouter(prefix="/api/channels", tags=["channels"])

@router.get("/{channel_id}/messages")
async def get_channel_messages(
    channel_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, le=100),
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db)
):
    """Get paginated messages from a channel."""
    with Session(engine) as session:
        # Check if channel exists
        channel = session.exec(select(Channel).where(Channel.id == channel_id)).first()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        
        # For non-public channels, check if user is a member
        if channel.channel_type != ChannelType.PUBLIC:
            member = session.exec(
                select(ChannelMember).where(
                    ChannelMember.channel_id == channel_id,
                    ChannelMember.user_id == current_user.id
                )
            ).first()
            if not member:
                raise HTTPException(status_code=403, detail="Not a member of this channel")
        
        # Calculate offset
        offset = (page - 1) * page_size
        
        # Get messages with user information
        messages = session.exec(
            select(Message)
            .where(Message.channel_id == channel_id)
            .order_by(Message.created_at.asc())
            .offset(offset)
            .limit(page_size)
        ).all()
        
        # Convert to dict and include user information
        return [
            {
                **message.model_dump(),
                "user": session.exec(select(User).where(User.id == message.user_id)).first().model_dump(
                    exclude={"hashed_password", "email"}
                )
            }
            for message in messages
        ]

@router.post("/{channel_id}/messages")
async def create_channel_message(
    channel_id: UUID,
    message: dict,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db)
):
    """Create a new message in a channel."""
    with Session(engine) as session:
        # Check if channel exists
        channel = session.exec(select(Channel).where(Channel.id == channel_id)).first()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        
        # For non-public channels, check if user is a member
        if channel.channel_type != ChannelType.PUBLIC:
            member = session.exec(
                select(ChannelMember).where(
                    ChannelMember.channel_id == channel_id,
                    ChannelMember.user_id == current_user.id
                )
            ).first()
            if not member:
                raise HTTPException(status_code=403, detail="Not a member of this channel")
        
        # Create message
        new_message = Message(
            content=message["content"],
            user_id=current_user.id,
            channel_id=channel_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC)
        )
        session.add(new_message)
        session.commit()
        session.refresh(new_message)
        
        # Get full message data with user info
        message_data = {
            **new_message.model_dump(),
            "user": current_user.model_dump(exclude={"hashed_password", "email"})
        }
        
        # Broadcast to channel subscribers via WebSocket
        await manager.broadcast_to_channel(
            channel_id,
            "message_sent",
            message_data
        )
        
        return message_data 