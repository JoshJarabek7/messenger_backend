from typing import Optional
from uuid import UUID

from app.models.domain import DirectMessageConversation, File, Message
from app.repositories.direct_message_repository import DirectMessageRepository
from app.services.base_service import BaseService


class DirectMessageService(BaseService):
    """Service for managing direct message operations."""

    def __init__(self, dm_repository: DirectMessageRepository) -> None:
        self.dm_repository: DirectMessageRepository = dm_repository

    def get_or_create_conversation(
        self, user1_id: UUID, user2_id: UUID
    ) -> DirectMessageConversation:
        """Get or create a DM conversation between two users."""
        return self.dm_repository.get_or_create_conversation(
            user1_id=user1_id, user2_id=user2_id
        )

    def create_message(self, conversation_id: UUID, message: Message) -> Message:
        """Create a new message in the DM conversation."""
        return self.dm_repository.create_message(
            conversation_id=conversation_id, message=message
        )

    def get_conversation_with_messages(
        self,
        conversation_id: UUID,
        limit: int = 50,
        before_message_id: Optional[UUID] = None,
    ) -> Optional[DirectMessageConversation]:
        """Get DM conversation with its messages."""
        return self.dm_repository.get_conversation_with_messages(
            conversation_id=conversation_id,
            limit=limit,
            before_message_id=before_message_id,
        )

    def add_file(self, conversation_id: UUID, file: File) -> File:
        """Add a file to the DM conversation."""
        return self.dm_repository.add_file(conversation_id=conversation_id, file=file)
