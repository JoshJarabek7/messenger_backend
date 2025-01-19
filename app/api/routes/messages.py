from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException


from app.api.dependencies import get_current_user
from app.db.session import get_db
from sqlmodel import Session
from app.models.domain import User
from app.models.schemas.requests.reaction import (
    CreateReactionRequest,
)
from app.models.schemas.responses.message import MessageResponse
from app.models.schemas.responses.reaction import ReactionResponse
from app.repositories.message_repository import MessageRepository
from app.services.message_service import MessageService

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Get a message by ID"""
    message_service = MessageService(MessageRepository(db))
    message = message_service.get_message_with_reactions(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return MessageResponse.model_validate(message)


@router.delete("/{message_id}", response_model=dict[str, str])
async def delete_message(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Delete a message"""
    message_repository = MessageRepository(db)
    message = message_repository.get_message_with_reactions(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Check if user owns the message
    if message.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this message"
        )

    message_repository.delete(message_id)
    return {"message": "Message deleted successfully"}


@router.post("/{message_id}/reactions", response_model=ReactionResponse)
async def add_reaction(
    message_id: UUID,
    reaction_data: CreateReactionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReactionResponse:
    """Add a reaction to a message"""
    message_service = MessageService(MessageRepository(db))
    reaction = message_service.add_reaction(
        message_id=message_id,
        user_id=current_user.id,
        emoji=reaction_data.reaction_type,
    )
    return ReactionResponse.model_validate(reaction)


@router.delete("/{message_id}/reactions/{reaction_id}", response_model=dict[str, str])
async def remove_reaction(
    message_id: UUID,
    reaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Remove a reaction from a message"""
    message_service = MessageService(MessageRepository(db))
    message = message_service.get_message_with_reactions(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Find the reaction
    reaction = next((r for r in message.reactions or [] if r.id == reaction_id), None)
    if not reaction:
        raise HTTPException(status_code=404, detail="Reaction not found")

    # Check if user owns the reaction
    if reaction.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to remove this reaction"
        )

    message_service.remove_reaction(
        message_id=message_id,
        user_id=current_user.id,
        emoji=reaction.emoji,
    )
    return {"message": "Reaction removed successfully"}


@router.get("/{message_id}/thread", response_model=list[MessageResponse])
async def get_thread(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MessageResponse]:
    """Get all messages in a thread"""
    message_service = MessageService(MessageRepository(db))
    messages = message_service.get_thread_messages(message_id)
    return [MessageResponse.model_validate(msg) for msg in messages]
