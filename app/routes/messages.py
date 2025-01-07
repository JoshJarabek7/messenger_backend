from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy import Engine
from typing import List
from uuid import UUID
from datetime import datetime, UTC, timedelta
from pydantic import BaseModel

from app.db import get_db
from app.models import Message, Channel, User, ChannelMember, ChannelType
from app.auth_utils import get_current_user
from app.websocket_manager import manager, WebSocketMessageType

router = APIRouter(prefix="/api/messages", tags=["messages"])

class UserInfo(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    is_online: bool

class DMChannel(BaseModel):
    id: str
    user: UserInfo
    last_message: dict | None = None
    updated_at: datetime

class MessageCreate(BaseModel):
    content: str

@router.get("/recent-dms", response_model=List[DMChannel])
async def get_recent_dms(
    limit: int = Query(default=10, le=50),
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db)
):
    """Get recent DM conversations for the current user."""
    with Session(engine) as session:
        # Get DM channels where the user is a participant
        dm_channels = session.exec(
            select(Channel)
            .where(
                Channel.channel_type == ChannelType.DIRECT,
                (Channel.participant_1_id == current_user.id) | (Channel.participant_2_id == current_user.id)
            )
            .order_by(Channel.updated_at.desc())
            .limit(limit)
        ).all()

        # For each channel, get the other participant's info
        result = []
        for channel in dm_channels:
            other_user_id = channel.participant_2_id if channel.participant_1_id == current_user.id else channel.participant_1_id
            other_user = session.exec(select(User).where(User.id == other_user_id)).first()
            
            if other_user:
                # Get the most recent message
                latest_message = session.exec(
                    select(Message)
                    .where(Message.channel_id == channel.id)
                    .order_by(Message.created_at.desc())
                    .limit(1)
                ).first()

                result.append(DMChannel(
                    id=str(channel.id),
                    user=UserInfo(
                        id=str(other_user.id),
                        username=other_user.username,
                        display_name=other_user.display_name,
                        avatar_url=other_user.avatar_url,
                        is_online=other_user.is_online
                    ),
                    last_message=latest_message.model_dump() if latest_message else None,
                    updated_at=channel.updated_at
                ))

        return sorted(result, key=lambda x: x.updated_at, reverse=True) 

@router.post("/{channel_id}/messages")
async def create_channel_message(
    channel_id: UUID,
    message: MessageCreate,
    engine: Engine = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    with Session(engine) as session:
        # Check if channel exists and user is a member
        channel = session.exec(
            select(Channel)
            .where(Channel.id == channel_id)
        ).first()
        
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        
        # Create message
        db_message = Message(
            content=message.content,
            channel_id=channel_id,
            user_id=current_user.id
        )
        session.add(db_message)
        session.commit()
        session.refresh(db_message)
        
        # Convert to response model
        message_data = {
            "id": str(db_message.id),
            "content": db_message.content,
            "channel_id": str(db_message.channel_id),
            "user": {
                "id": str(current_user.id),
                "username": current_user.username,
                "display_name": current_user.display_name,
                "avatar_url": current_user.avatar_url
            },
            "created_at": db_message.created_at.isoformat(),
            "updated_at": db_message.updated_at.isoformat()
        }
        
        print(f"Broadcasting message to channel {channel_id}")
        print(f"Message data: {message_data}")
        
        # Broadcast to channel subscribers
        await manager.broadcast_to_channel(
            channel_id,
            WebSocketMessageType.MESSAGE_SENT,
            message_data
        )
        
        return message_data 