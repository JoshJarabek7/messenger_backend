from typing import Optional
from uuid import UUID

from sqlmodel import Session, select

from app.models.domain import Channel, File, Message
from app.repositories.base_repository import BaseRepository


class ChannelRepository(BaseRepository[Channel]):
    """Repository for managing channel operations."""

    def __init__(self, db: Session):
        super().__init__(Channel, db)

    def create_message(self, channel_id: UUID, message: Message) -> Message:
        """Create a new message in the channel."""
        message.channel_id = channel_id
        self.db.add(message)
        self.db.flush()
        return message

    def get_channel_with_messages(
        self,
        channel_id: UUID,
        limit: int = 50,
        before_message_id: Optional[UUID] = None,
    ) -> Optional[Channel]:
        """Get channel with its messages."""
        query = select(Channel).where(Channel.id == channel_id)

        if before_message_id:
            message = self.db.get(Message, before_message_id)
            if message:
                query = query.where(Message.created_at < message.created_at)

        result = self.db.exec(query.limit(limit))
        return result.one_or_none()

    def add_file(self, channel_id: UUID, file: File) -> File:
        """Add a file to the channel."""
        file.channel_id = channel_id
        self.db.add(file)
        self.db.flush()
        return file
