from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy import Engine, or_, and_
from typing import List
from uuid import UUID
from datetime import datetime, UTC
from pydantic import BaseModel

from app.db import get_db
from app.models import DirectMessage, DirectMessageConversation, User
from app.auth_utils import get_current_user
from app.websocket_manager import manager, WebSocketMessageType

router = APIRouter(prefix="/api/direct-messages", tags=["direct-messages"])

class MessageCreate(BaseModel):
    content: str

class ConversationCreate(BaseModel):
    recipient_id: str

@router.post("")
async def create_or_get_conversation(
    data: ConversationCreate,
    engine: Engine = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new DM conversation or get an existing one."""
    with Session(engine) as session:
        recipient_id = UUID(data.recipient_id)
        # Check if conversation already exists
        conversation = session.exec(
            select(DirectMessageConversation).where(
                or_(
                    and_(
                        DirectMessageConversation.participant_1_id == current_user.id,
                        DirectMessageConversation.participant_2_id == recipient_id
                    ),
                    and_(
                        DirectMessageConversation.participant_1_id == recipient_id,
                        DirectMessageConversation.participant_2_id == current_user.id
                    )
                )
            )
        ).first()

        if not conversation:
            # Create new conversation
            conversation = DirectMessageConversation(
                participant_1_id=current_user.id,
                participant_2_id=recipient_id
            )
            session.add(conversation)
            session.commit()
            session.refresh(conversation)

        # Subscribe both users to the conversation
        manager.subscribe_to_conversation(current_user.id, conversation.id)
        manager.subscribe_to_conversation(recipient_id, conversation.id)

        return {
            "id": str(conversation.id),
            "participant_1_id": str(conversation.participant_1_id),
            "participant_2_id": str(conversation.participant_2_id),
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at
        }

@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, le=100),
    engine: Engine = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get messages for a DM conversation."""
    with Session(engine) as session:
        # Verify user is part of the conversation
        conversation = session.exec(
            select(DirectMessageConversation).where(
                DirectMessageConversation.id == conversation_id,
                or_(
                    DirectMessageConversation.participant_1_id == current_user.id,
                    DirectMessageConversation.participant_2_id == current_user.id
                )
            )
        ).first()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Get messages with pagination
        messages = session.exec(
            select(DirectMessage)
            .where(DirectMessage.conversation_id == conversation_id)
            .order_by(DirectMessage.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        # Format messages for response
        return [
            {
                "id": str(msg.id),
                "content": msg.content,
                "user": {
                    "id": str(msg.sender_id),
                    "username": msg.sender.username,
                    "display_name": msg.sender.display_name,
                    "avatar_url": msg.sender.avatar_url
                },
                "created_at": msg.created_at.isoformat(),
                "updated_at": msg.updated_at.isoformat()
            }
            for msg in messages
        ]

@router.post("/{conversation_id}/messages")
async def create_message(
    conversation_id: UUID,
    message: MessageCreate,
    engine: Engine = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send a message in a DM conversation."""
    with Session(engine) as session:
        # Verify user is part of the conversation
        conversation = session.exec(
            select(DirectMessageConversation).where(
                DirectMessageConversation.id == conversation_id,
                or_(
                    DirectMessageConversation.participant_1_id == current_user.id,
                    DirectMessageConversation.participant_2_id == current_user.id
                )
            )
        ).first()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Create message
        db_message = DirectMessage(
            content=message.content,
            sender_id=current_user.id,
            conversation_id=conversation_id
        )
        session.add(db_message)
        
        # Update conversation timestamp
        conversation.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(db_message)

        # Format message for response
        message_data = {
            "id": str(db_message.id),
            "content": db_message.content,
            "user": {
                "id": str(current_user.id),
                "username": current_user.username,
                "display_name": current_user.display_name,
                "avatar_url": current_user.avatar_url
            },
            "created_at": db_message.created_at.isoformat(),
            "updated_at": db_message.updated_at.isoformat(),
            "conversation_id": str(conversation_id)  # Add conversation_id to the message data
        }

        # Broadcast to conversation subscribers
        await manager.broadcast_to_conversation(
            conversation_id,
            WebSocketMessageType.MESSAGE_SENT,
            message_data
        )

        return message_data

@router.get("/recent-dms")
async def get_recent_dms(
    engine: Engine = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get recent DM conversations for the current user."""
    with Session(engine) as session:
        # Get conversations where the user is either participant
        conversations = session.exec(
            select(DirectMessageConversation)
            .where(
                or_(
                    DirectMessageConversation.participant_1_id == current_user.id,
                    DirectMessageConversation.participant_2_id == current_user.id
                )
            )
            .order_by(DirectMessageConversation.updated_at.desc())
        ).all()

        result = []
        for conv in conversations:
            # Get the other participant's details
            other_user_id = conv.participant_2_id if conv.participant_1_id == current_user.id else conv.participant_1_id
            other_user = session.get(User, other_user_id)

            # Get the last message in the conversation
            last_message = session.exec(
                select(DirectMessage)
                .where(DirectMessage.conversation_id == conv.id)
                .order_by(DirectMessage.created_at.desc())
                .limit(1)
            ).first()

            result.append({
                "id": str(conv.id),
                "user": {
                    "id": str(other_user.id),
                    "username": other_user.username,
                    "display_name": other_user.display_name,
                    "avatar_url": other_user.avatar_url
                },
                "last_message": {
                    "content": last_message.content,
                    "created_at": last_message.created_at.isoformat()
                } if last_message else None
            })

        return result 