from fastapi import APIRouter, Depends, Query, HTTPException
from sqlmodel import Session, select
from sqlalchemy import Engine
from typing import List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from app.utils.db import get_db
from app.models import Message, User, Reaction
from app.utils.auth import get_current_user
from app.websocket import manager, WebSocketMessageType
from app.schemas import MessageInfo
from app.utils.access import verify_conversation_access

router = APIRouter(prefix="/api/messages", tags=["messages"])

class MessageCreate(BaseModel):
    content: str

class ReactionCreate(BaseModel):
    emoji: str

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
        
        # Convert to response model with proper user data
        message_list = []
        for message in messages:
            # Count replies for this message
            reply_count_result = session.exec(
                select(Message).where(Message.parent_id == message.id)
            ).all()
            reply_count = len(reply_count_result)
            
            message_data = {
                "id": str(message.id),
                "content": message.content,
                "conversation_id": str(message.conversation_id),
                "parent_id": str(message.parent_id) if message.parent_id else None,
                "created_at": message.created_at,
                "updated_at": message.updated_at,
                "reply_count": reply_count,  # Add reply count to response
                "user": {
                    "id": str(message.user.id),
                    "email": message.user.email,
                    "username": message.user.username,
                    "display_name": message.user.display_name,
                    "avatar_url": message.user.avatar_url,
                    "is_online": message.user.is_online
                },
                "attachments": [{
                    "id": str(a.id),
                    "original_filename": a.original_filename,
                    "file_type": a.file_type,
                    "mime_type": a.mime_type,
                    "file_size": a.file_size,
                    "uploaded_at": a.uploaded_at
                } for a in message.attachments],
                "reactions": [{
                    "id": str(r.id),
                    "emoji": r.emoji,
                    "user": {
                        "id": str(r.user.id),
                        "email": r.user.email,
                        "username": r.user.username,
                        "display_name": r.user.display_name,
                        "avatar_url": r.user.avatar_url,
                        "is_online": r.user.is_online
                    }
                } for r in message.reactions]
            }
            message_list.append(MessageInfo.model_validate(message_data))
        
        return message_list

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
        
        # Convert to response model with proper user data
        message_data = {
            "id": str(db_message.id),
            "content": db_message.content,
            "conversation_id": str(db_message.conversation_id),
            "parent_id": str(db_message.parent_id) if db_message.parent_id else None,
            "created_at": db_message.created_at,
            "updated_at": db_message.updated_at,
            "user": {
                "id": str(current_user.id),
                "email": current_user.email,
                "username": current_user.username,
                "display_name": current_user.display_name,
                "avatar_url": current_user.avatar_url,
                "is_online": True  # Since they're actively sending a message
            },
            "attachments": [],
            "reactions": []
        }
        
        message_info = MessageInfo.model_validate(message_data)
        
        # Broadcast to conversation subscribers
        await manager.broadcast_to_conversation(
            conversation_id,
            WebSocketMessageType.MESSAGE_SENT,
            message_info.model_dump()
        )
        
        return message_info 

@router.post("/{message_id}/reactions", response_model=MessageInfo)
async def add_reaction(
    message_id: UUID,
    reaction: ReactionCreate,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db)
):
    """Add a reaction to a message."""
    with Session(engine) as session:
        # Get message and verify access
        message = session.get(Message, message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        # Verify access to conversation
        verify_conversation_access(session, message.conversation_id, current_user.id)
        
        # Check if user already reacted with this emoji
        existing_reaction = session.exec(
            select(Reaction).where(
                Reaction.message_id == message_id,
                Reaction.user_id == current_user.id,
                Reaction.emoji == reaction.emoji
            )
        ).first()
        
        if existing_reaction:
            raise HTTPException(status_code=400, detail="Reaction already exists")
        
        # Create reaction
        db_reaction = Reaction(
            emoji=reaction.emoji,
            message_id=message_id,
            user_id=current_user.id
        )
        session.add(db_reaction)
        session.commit()
        session.refresh(message)
        
        # Convert to response model
        message_data = {
            "id": str(message.id),
            "content": message.content,
            "conversation_id": str(message.conversation_id),
            "parent_id": str(message.parent_id) if message.parent_id else None,
            "created_at": message.created_at,
            "updated_at": message.updated_at,
            "user": {
                "id": str(message.user.id),
                "email": message.user.email,
                "username": message.user.username,
                "display_name": message.user.display_name,
                "avatar_url": message.user.avatar_url,
                "is_online": message.user.is_online
            },
            "attachments": [],
            "reactions": [{
                "id": str(r.id),
                "emoji": r.emoji,
                "user": {
                    "id": str(r.user.id),
                    "email": r.user.email,
                    "username": r.user.username,
                    "display_name": r.user.display_name,
                    "avatar_url": r.user.avatar_url,
                    "is_online": r.user.is_online
                }
            } for r in message.reactions]
        }
        
        message_info = MessageInfo.model_validate(message_data)
        
        # Broadcast update
        await manager.broadcast_to_conversation(
            message.conversation_id,
            WebSocketMessageType.MESSAGE_SENT,
            message_info.model_dump()
        )
        
        return message_info

@router.delete("/{message_id}/reactions/{reaction_id}", response_model=MessageInfo)
async def remove_reaction(
    message_id: UUID,
    reaction_id: UUID,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db)
):
    """Remove a reaction from a message."""
    with Session(engine) as session:
        # Get message and verify access
        message = session.get(Message, message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        # Verify access to conversation
        verify_conversation_access(session, message.conversation_id, current_user.id)
        
        # Get reaction
        reaction = session.get(Reaction, reaction_id)
        if not reaction or reaction.message_id != message_id:
            raise HTTPException(status_code=404, detail="Reaction not found")
        
        # Verify ownership
        if reaction.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Cannot remove another user's reaction")
        
        # Remove reaction
        session.delete(reaction)
        session.commit()
        session.refresh(message)
        
        # Convert to response model
        message_data = {
            "id": str(message.id),
            "content": message.content,
            "conversation_id": str(message.conversation_id),
            "parent_id": str(message.parent_id) if message.parent_id else None,
            "created_at": message.created_at,
            "updated_at": message.updated_at,
            "reply_count": len(session.exec(select(Message).where(Message.parent_id == message.id)).all()),
            "user": {
                "id": str(message.user.id),
                "email": message.user.email,
                "username": message.user.username,
                "display_name": message.user.display_name,
                "avatar_url": message.user.avatar_url,
                "is_online": message.user.is_online
            },
            "attachments": [],
            "reactions": [{
                "id": str(r.id),
                "emoji": r.emoji,
                "user": {
                    "id": str(r.user.id),
                    "email": r.user.email,
                    "username": r.user.username,
                    "display_name": r.user.display_name,
                    "avatar_url": r.user.avatar_url,
                    "is_online": r.user.is_online
                }
            } for r in message.reactions]
        }
        
        message_info = MessageInfo.model_validate(message_data)
        
        # Broadcast update
        await manager.broadcast_to_conversation(
            message.conversation_id,
            WebSocketMessageType.MESSAGE_SENT,
            message_info.model_dump()
        )
        
        return message_info

@router.post("/{message_id}/reply", response_model=MessageInfo)
async def create_reply(
    message_id: UUID,
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db)
):
    """Create a reply to a message (thread)."""
    with Session(engine) as session:
        # Get parent message and verify access
        parent_message = session.get(Message, message_id)
        if not parent_message:
            raise HTTPException(status_code=404, detail="Parent message not found")
        
        # Verify access to conversation
        conversation = verify_conversation_access(session, parent_message.conversation_id, current_user.id)
        
        # Create reply message
        db_message = Message(
            content=message.content,
            conversation_id=parent_message.conversation_id,
            parent_id=message_id,
            user_id=current_user.id
        )
        session.add(db_message)
        
        # Update conversation timestamp
        conversation.updated_at = datetime.now()
        session.add(conversation)
        session.commit()
        session.refresh(db_message)
        
        # Convert to response model
        message_data = {
            "id": str(db_message.id),
            "content": db_message.content,
            "conversation_id": str(db_message.conversation_id),
            "parent_id": str(db_message.parent_id),
            "created_at": db_message.created_at,
            "updated_at": db_message.updated_at,
            "user": {
                "id": str(current_user.id),
                "email": current_user.email,
                "username": current_user.username,
                "display_name": current_user.display_name,
                "avatar_url": current_user.avatar_url,
                "is_online": True
            },
            "attachments": [],
            "reactions": []
        }
        
        message_info = MessageInfo.model_validate(message_data)
        
        # Broadcast to conversation subscribers
        await manager.broadcast_to_conversation(
            parent_message.conversation_id,
            WebSocketMessageType.MESSAGE_SENT,
            message_info.model_dump()
        )
        
        return message_info

@router.get("/{message_id}/thread", response_model=List[MessageInfo])
async def get_thread_messages(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db)
):
    """Get all messages in a thread."""
    with Session(engine) as session:
        # Get parent message and verify access
        parent_message = session.get(Message, message_id)
        if not parent_message:
            raise HTTPException(status_code=404, detail="Parent message not found")
        
        # Verify access to conversation
        verify_conversation_access(session, parent_message.conversation_id, current_user.id)
        
        # Get thread messages
        query = select(Message).where(
            Message.parent_id == message_id
        ).order_by(Message.created_at.asc())
        
        messages = session.exec(query).all()
        
        # Convert to response model with proper user data
        message_list = []
        for message in messages:
            message_data = {
                "id": str(message.id),
                "content": message.content,
                "conversation_id": str(message.conversation_id),
                "parent_id": str(message.parent_id) if message.parent_id else None,
                "created_at": message.created_at,
                "updated_at": message.updated_at,
                "user": {
                    "id": str(message.user.id),
                    "email": message.user.email,
                    "username": message.user.username,
                    "display_name": message.user.display_name,
                    "avatar_url": message.user.avatar_url,
                    "is_online": message.user.is_online
                },
                "attachments": [{
                    "id": str(a.id),
                    "original_filename": a.original_filename,
                    "file_type": a.file_type,
                    "mime_type": a.mime_type,
                    "file_size": a.file_size,
                    "uploaded_at": a.uploaded_at
                } for a in message.attachments],
                "reactions": [{
                    "id": str(r.id),
                    "emoji": r.emoji,
                    "user": {
                        "id": str(r.user.id),
                        "email": r.user.email,
                        "username": r.user.username,
                        "display_name": r.user.display_name,
                        "avatar_url": r.user.avatar_url,
                        "is_online": r.user.is_online
                    }
                } for r in message.reactions]
            }
            message_list.append(MessageInfo.model_validate(message_data))
        
        return message_list 