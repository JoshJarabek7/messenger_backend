from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Session, and_, or_, select

from app.models.domain import DirectMessageConversation, File, Message
from app.repositories.base_repository import BaseRepository


class DirectMessageRepository(BaseRepository[DirectMessageConversation]):
    def __init__(self, db: Session):
        super().__init__(DirectMessageConversation, db)

    def get_or_create_conversation(
        self, user1_id: UUID, user2_id: UUID
    ) -> DirectMessageConversation:
        """Get or create a direct message conversation between two users."""
        query = select(DirectMessageConversation).where(
            or_(
                and_(
                    DirectMessageConversation.user1_id == user1_id,
                    DirectMessageConversation.user2_id == user2_id,
                ),
                and_(
                    DirectMessageConversation.user1_id == user2_id,
                    DirectMessageConversation.user2_id == user1_id,
                ),
            )
        )
        result = self.db.exec(query)
        conversation = result.one_or_none()

        if not conversation:
            conversation = DirectMessageConversation(
                id=uuid4(),
                user1_id=user1_id,
                user2_id=user2_id,
            )
            self.db.add(conversation)
            self.db.flush()

        return conversation

    def create_message(self, conversation_id: UUID, message: Message) -> Message:
        """Create a new message in the DM conversation."""
        message.dm_conversation_id = conversation_id
        self.db.add(message)
        self.db.flush()
        return message

    def get_conversation_with_messages(
        self,
        conversation_id: UUID,
        limit: int = 50,
        before_message_id: Optional[UUID] = None,
    ) -> Optional[DirectMessageConversation]:
        """Get DM conversation with its messages."""
        query = select(DirectMessageConversation).where(
            DirectMessageConversation.id == conversation_id
        )

        if before_message_id:
            message = self.db.get(Message, before_message_id)
            if message:
                query = query.where(Message.created_at < message.created_at)

        result = self.db.exec(query.limit(limit))
        return result.one_or_none()

    def add_file(self, conversation_id: UUID, file: File) -> File:
        """Add a file to the DM conversation."""
        file.dm_conversation_id = conversation_id
        self.db.add(file)
        self.db.flush()
        return file

    def get_all_conversations_for_user(
        self, user_id: UUID
    ) -> list[DirectMessageConversation]:
        query = select(DirectMessageConversation).where(
            or_(
                DirectMessageConversation.user1_id == user_id,
                DirectMessageConversation.user2_id == user_id,
            )
        )
        result = self.db.exec(query).all()
        return list(result)
