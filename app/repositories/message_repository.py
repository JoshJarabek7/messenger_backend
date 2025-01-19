from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Session, select

from app.models.domain import Message, Reaction
from app.repositories.base_repository import BaseRepository


class MessageRepository(BaseRepository[Message]):
    """Repository for managing message operations."""

    def __init__(self, db: Session):
        super().__init__(Message, db)

    def get_message_with_reactions(self, message_id: UUID) -> Optional[Message]:
        """Get a message with its reactions."""
        query = select(Message).where(Message.id == message_id)
        result = self.db.exec(query)
        return result.one_or_none()

    def add_reaction(self, message_id: UUID, user_id: UUID, emoji: str) -> Reaction:
        """Add a reaction to a message."""
        # Check if reaction already exists
        query = select(Reaction).where(
            Reaction.message_id == message_id,
            Reaction.user_id == user_id,
            Reaction.emoji == emoji,
        )
        result = self.db.exec(query)
        existing_reaction = result.one_or_none()

        if existing_reaction:
            return existing_reaction

        reaction = Reaction(
            id=uuid4(),
            message_id=message_id,
            user_id=user_id,
            emoji=emoji,
        )
        self.db.add(reaction)
        self.db.flush()
        return reaction

    def remove_reaction(self, message_id: UUID, user_id: UUID, emoji: str) -> None:
        """Remove a reaction from a message."""
        query = select(Reaction).where(
            Reaction.message_id == message_id,
            Reaction.user_id == user_id,
            Reaction.emoji == emoji,
        )
        result = self.db.exec(query)
        reaction = result.one_or_none()

        if reaction:
            self.db.delete(reaction)
            self.db.flush()

    def get_message_with_thread(
        self, message_id: UUID, max_depth: int = 10
    ) -> Optional[Message]:
        """
        Get a message with its entire thread tree up to max_depth levels deep.
        This includes all replies and nested replies.
        """
        if max_depth <= 0:
            return None

        query = select(Message).where(Message.id == message_id)
        result = self.db.exec(query)
        message = result.one_or_none()

        if not message:
            return None

        # Recursively get replies for each reply
        if message.replies:
            for reply in message.replies:
                reply_thread = self.get_message_with_thread(reply.id, max_depth - 1)
                if reply_thread and reply_thread.replies:
                    reply.replies = reply_thread.replies

        return message

    def get_thread_messages(
        self, root_message_id: UUID, max_depth: int = 10
    ) -> list[Message]:
        """
        Get all messages in a thread as a flat list, ordered by creation time.
        This includes the root message, all replies, and nested replies up to max_depth.
        """
        if max_depth <= 0:
            return []

        # Get the root message and its thread
        thread_root = self.get_message_with_thread(root_message_id, max_depth)
        if not thread_root:
            return []

        # Helper function to flatten the thread tree
        def flatten_thread(message: Message, messages: list[Message]) -> None:
            messages.append(message)
            if message.replies:
                for reply in sorted(message.replies, key=lambda m: m.created_at):
                    flatten_thread(reply, messages)

        # Flatten the thread tree into a list
        thread_messages: list[Message] = []
        flatten_thread(thread_root, thread_messages)
        return thread_messages
