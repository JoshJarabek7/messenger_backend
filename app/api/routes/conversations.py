from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from app.api.dependencies import get_current_user
from app.models.domain import Message, User
from app.models.schemas.responses.conversation import DirectMessageConversationResponse
from app.models.schemas.responses.message import MessageResponse
from app.repositories.direct_message_repository import DirectMessageRepository
from app.services.direct_message_service import DirectMessageService
from app.db.session import get_db
from sqlmodel import Session

router = APIRouter(prefix="/api/dm", tags=["direct_messages"])


class CreateConversationRequest(BaseModel):
    user_id: UUID


class CreateMessageRequest(BaseModel):
    content: str
    parent_id: UUID | None = None


@router.get("/conversations", response_model=list[DirectMessageConversationResponse])
async def list_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DirectMessageConversationResponse]:
    """List all DM conversations for the current user"""
    # Return conversations where user is either user1 or user2
    conversations_as_user1 = current_user.dm_conversations_as_user1 or []
    conversations_as_user2 = current_user.dm_conversations_as_user2 or []
    conversations = conversations_as_user1 + conversations_as_user2
    return [
        DirectMessageConversationResponse.model_validate(conv) for conv in conversations
    ]


@router.post("/conversations", response_model=DirectMessageConversationResponse)
async def create_conversation(
    conversation_data: CreateConversationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DirectMessageConversationResponse:
    """Create or get a DM conversation with another user"""
    dm_service = DirectMessageService(DirectMessageRepository(db))
    conversation = dm_service.get_or_create_conversation(
        user1_id=current_user.id,
        user2_id=conversation_data.user_id,
    )
    return DirectMessageConversationResponse.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}", response_model=DirectMessageConversationResponse
)
async def get_conversation(
    conversation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DirectMessageConversationResponse:
    """Get a DM conversation by ID"""
    dm_service = DirectMessageService(DirectMessageRepository(db))
    conversation = dm_service.get_conversation_with_messages(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if user is part of the conversation
    if (
        conversation.user1_id != current_user.id
        and conversation.user2_id != current_user.id
    ):
        raise HTTPException(
            status_code=403, detail="Not authorized to access this conversation"
        )

    return DirectMessageConversationResponse.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}/messages", response_model=list[MessageResponse]
)
async def list_conversation_messages(
    conversation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 50,
    before_message_id: UUID | None = None,
) -> list[MessageResponse]:
    """List messages in a DM conversation"""
    dm_service = DirectMessageService(DirectMessageRepository(db))
    conversation = dm_service.get_conversation_with_messages(
        conversation_id=conversation_id,
        limit=limit,
        before_message_id=before_message_id,
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if user is part of the conversation
    if (
        conversation.user1_id != current_user.id
        and conversation.user2_id != current_user.id
    ):
        raise HTTPException(
            status_code=403, detail="Not authorized to access this conversation"
        )

    messages = conversation.messages if conversation.messages else []
    logger.info(f"Messages in list_conversation_messages: {messages}")
    return [MessageResponse.model_validate(msg) for msg in messages]


@router.post(
    "/conversations/{conversation_id}/messages", response_model=MessageResponse
)
async def create_conversation_message(
    conversation_id: UUID,
    message_data: CreateMessageRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    """Create a new message in the DM conversation"""
    dm_service = DirectMessageService(DirectMessageRepository(db))
    conversation = dm_service.get_conversation_with_messages(conversation_id)

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if user is part of the conversation
    if (
        conversation.user1_id != current_user.id
        and conversation.user2_id != current_user.id
    ):
        raise HTTPException(
            status_code=403, detail="Not authorized to access this conversation"
        )

    message = Message(
        id=uuid4(),
        content=message_data.content,
        user_id=current_user.id,
        parent_id=message_data.parent_id,
    )
    created_message = dm_service.create_message(
        conversation_id=conversation_id, message=message
    )
    return MessageResponse.model_validate(created_message)
