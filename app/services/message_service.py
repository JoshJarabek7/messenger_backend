from typing import Optional
from uuid import UUID

from app.models.domain import Message, Reaction
from app.repositories.message_repository import MessageRepository
from app.services.base_service import BaseService


class MessageService(BaseService):
    """Service for managing message operations."""

    def __init__(self, message_repository: MessageRepository):
        self.message_repository = message_repository

    def get_message_with_reactions(self, message_id: UUID) -> Optional[Message]:
        """Get a message with its reactions."""
        return self.message_repository.get_message_with_reactions(message_id)

    def add_reaction(self, message_id: UUID, user_id: UUID, emoji: str) -> Reaction:
        """Add a reaction to a message."""
        return self.message_repository.add_reaction(message_id, user_id, emoji)

    def remove_reaction(self, message_id: UUID, user_id: UUID, emoji: str) -> None:
        """Remove a reaction from a message."""
        self.message_repository.remove_reaction(message_id, user_id, emoji)

    def get_replies(self, message_id: UUID) -> list[Message]:
        """Get replies to a message."""
        return self.message_repository.get_thread_messages(root_message_id=message_id)

    def get_message_with_thread(
        self, message_id: UUID, max_depth: int = 10
    ) -> Optional[Message]:
        """
        Get a message with its entire conversation thread.
        This includes all replies and nested replies up to max_depth levels.
        """
        return self.message_repository.get_message_with_thread(message_id, max_depth)

    def get_thread_messages(
        self, root_message_id: UUID, max_depth: int = 10
    ) -> list[Message]:
        """
        Get all messages in a thread as a flat list, ordered by creation time.
        This includes the root message, all replies, and nested replies up to max_depth.
        """
        return self.message_repository.get_thread_messages(root_message_id, max_depth)
