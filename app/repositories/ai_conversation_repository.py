from uuid import UUID
from typing import List, cast

from sqlmodel import Session, select, col
from sqlalchemy import desc

from app.models.domain import AIConversation, Message
from app.repositories.base_repository import BaseRepository


class AIConversationRepository(BaseRepository[AIConversation]):
    """Repository for managing AI conversation operations."""

    def __init__(self, db: Session):
        super().__init__(model_class=AIConversation, db=db)

    def get_conversation_by_user_id(self, user_id: UUID) -> AIConversation | None:
        """Get an AI conversation by user ID"""
        query = select(AIConversation).where(AIConversation.user_id == user_id)
        result = self.db.exec(query)
        return result.one_or_none()

    def get_conversation_with_messages(
        self,
        conversation_id: UUID,
        limit: int = 50,
        before_message_id: UUID | None = None,
    ) -> AIConversation | None:
        """Get an AI conversation with its messages"""
        # First get the conversation
        query = select(AIConversation).where(AIConversation.id == conversation_id)
        result = self.db.exec(query)
        conversation = result.one_or_none()

        if not conversation:
            return None

        # Then get the messages
        message_query = select(Message).where(
            Message.ai_conversation_id == conversation_id
        )
        if before_message_id:
            message_query = message_query.where(Message.id < before_message_id)
        message_query = message_query.order_by(desc(col(Message.created_at))).limit(
            limit
        )
        message_result = self.db.exec(message_query)
        messages = cast(List[Message], message_result.all())

        # Set messages directly
        conversation.messages = messages
        return conversation

    def create_message(self, message: Message) -> Message:
        """Create a message in an AI conversation"""
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message
