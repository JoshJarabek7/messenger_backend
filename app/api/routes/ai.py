from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.dependencies import get_current_user
from app.models.domain import User
from app.models.schemas.responses.ai import AIConversationResponse, MessageResponse
from app.services.ai_conversation_service import AIConversationService
from app.db.session import get_db
from sqlmodel import Session

router = APIRouter(prefix="/api/ai", tags=["ai"])


class CreateMessageRequest(BaseModel):
    content: str
    parent_id: UUID | None = None


@router.get("/conversation", response_model=AIConversationResponse)
async def get_conversation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get or create AI conversation for the current user"""
    ai_service = AIConversationService(db)
    conversation = ai_service.get_or_create_conversation(current_user.id)
    return AIConversationResponse.model_validate(conversation)


@router.get("/conversation/messages", response_model=list[MessageResponse])
async def list_conversation_messages(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MessageResponse]:
    """List all messages in the user's AI conversation"""
    ai_service = AIConversationService(db)
    conversation = ai_service.get_or_create_conversation(current_user.id)
    conv_with_messages = ai_service.get_conversation_with_messages(conversation.id)
    messages = (
        conv_with_messages.messages
        if conv_with_messages and conv_with_messages.messages
        else []
    )
    return [MessageResponse.model_validate(msg) for msg in messages]


@router.post("/conversation/messages", response_model=MessageResponse)
async def create_message(
    message: CreateMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Create a new message in the AI conversation"""
    ai_service = AIConversationService(db)
    conversation = ai_service.get_or_create_conversation(current_user.id)
    created_message = ai_service.create_message(
        conversation.id, message.content, current_user.id, message.parent_id
    )
    return MessageResponse.model_validate(created_message)


@router.get("/conversation/messages/stream")
async def stream_ai_response(
    message: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream AI response for a message"""
    ai_service = AIConversationService(db)
    conversation = ai_service.get_or_create_conversation(current_user.id)
    return StreamingResponse(
        ai_service.ai_response_stream(
            conversation_id=conversation.id,
            message_text=message,
        ),
        media_type="text/event-stream",
    )
