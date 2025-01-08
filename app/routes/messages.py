from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from sqlalchemy import Engine
from typing import List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from app.utils.db import get_db
from app.models import Message, User
from app.utils.auth import get_current_user
from app.websocket import manager, WebSocketMessageType
from app.schemas import MessageInfo
from app.utils.access import verify_conversation_access

router = APIRouter(prefix="/api/messages", tags=["messages"])

class MessageCreate(BaseModel):
    content: str

@router.get("/{conversation_id}", response_model=List[MessageInfo])
async def get_messages(
    conversation_id: UUID,
    limit: int = Query(default=50, le=100),
    before_timestamp: datetime | None = None,
    after_timestamp: datetime | None = None,
    thread_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db)
):
    """Get messages from any conversation (channel or DM)."""
    with Session(engine) as session:
        # Verify access to conversation
        conversation = verify_conversation_access(session, conversation_id, current_user.id)
        
        # Build base query
        query = select(Message).where(
            Message.conversation_id == conversation_id,
            Message.parent_id == thread_id  # None for main conversation, UUID for thread
        )
        
        # Add timestamp filters
        if before_timestamp:
            query = query.where(Message.created_at < before_timestamp)
        if after_timestamp:
            query = query.where(Message.created_at > after_timestamp)
        
        # Order by timestamp
        # For scrolling up (before_timestamp): get most recent messages first
        # For scrolling down (after_timestamp): get oldest messages first
        if before_timestamp or not after_timestamp:
            query = query.order_by(Message.created_at.desc())
        else:
            query = query.order_by(Message.created_at.asc())
        
        # Apply limit
        query = query.limit(limit)
        
        # Execute query
        messages = session.exec(query).all()
        
        # Reverse the order for before_timestamp queries to maintain chronological order
        if before_timestamp or not after_timestamp:
            messages.reverse()
        
        # Convert to response model
        return [MessageInfo.model_validate(message.model_dump()) for message in messages]

@router.post("/{conversation_id}", response_model=MessageInfo)
async def create_message(
    conversation_id: UUID,
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db)
):
    """Create a message in any conversation (channel or DM)."""
    with Session(engine) as session:
        # Verify access to conversation
        conversation = verify_conversation_access(session, conversation_id, current_user.id)
        
        # Create message
        db_message = Message(
            content=message.content,
            conversation_id=conversation_id,
            user_id=current_user.id
        )
        session.add(db_message)
        
        # Update conversation timestamp
        conversation.updated_at = datetime.now()
        session.add(conversation)
        session.commit()
        session.refresh(db_message)
        
        # Convert to response model
        message_data = MessageInfo.model_validate(db_message.model_dump())
        
        # Broadcast to conversation subscribers
        await manager.broadcast_to_conversation(
            conversation_id,
            WebSocketMessageType.MESSAGE_SENT,
            message_data.model_dump()
        )
        
        return message_data 