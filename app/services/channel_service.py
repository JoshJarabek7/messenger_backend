from typing import Optional, Sequence
from uuid import UUID

from sqlmodel import Session

from app.models.domain import Channel, File, Message
from app.repositories.channel_repository import ChannelRepository
from app.services.base_service import BaseService


class ChannelService(BaseService):
    """Service for managing channel operations."""

    def __init__(self, db: Session) -> None:
        self.channel_repository: ChannelRepository = ChannelRepository(db)

    def create_message(self, channel_id: UUID, message: Message) -> Message:
        """Create a new message in the channel."""
        return self.channel_repository.create_message(
            channel_id=channel_id, message=message
        )

    def get(self, channel_id: UUID) -> Optional[Channel]:
        """Get a channel by ID."""
        return self.channel_repository.get(channel_id)

    def update(
        self, channel_id: UUID, name: str | None = None, description: str | None = None
    ) -> Optional[Channel]:
        """Update a channel."""
        channel = self.get(channel_id)
        if not channel:
            return None

        if name is not None:
            channel.name = name
        if description is not None:
            channel.description = description

        return self.channel_repository.update(channel)

    def delete(self, channel_id: UUID) -> None:
        """Delete a channel."""
        self.channel_repository.delete(channel_id)

    def get_messages(
        self,
        channel_id: UUID,
        limit: int = 50,
        before_message_id: Optional[UUID] = None,
    ) -> Sequence[Message]:
        """Get messages in a channel."""
        channel = self.channel_repository.get_channel_with_messages(
            channel_id=channel_id, limit=limit, before_message_id=before_message_id
        )
        return channel.messages if channel and channel.messages else []

    def get_channel_with_messages(
        self,
        channel_id: UUID,
        limit: int = 50,
        before_message_id: Optional[UUID] = None,
    ) -> Optional[Channel]:
        """Get channel with its messages."""
        return self.channel_repository.get_channel_with_messages(
            channel_id=channel_id, limit=limit, before_message_id=before_message_id
        )

    def add_file(self, channel_id: UUID, file: File) -> File:
        """Add a file to the channel."""
        return self.channel_repository.add_file(channel_id=channel_id, file=file)
