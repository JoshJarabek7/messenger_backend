from uuid import UUID, uuid4
from typing import Generator

from sqlmodel import Session
from openai import OpenAI

from app.models.domain import AIConversation, Message
from app.services.base_service import BaseService
from app.services.vector_service import VectorService
from app.services.embedding_service import EmbeddingService
from app.repositories.ai_conversation_repository import AIConversationRepository
from app.core.config import get_settings


class AIConversationService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)
        self.ai_repository = AIConversationRepository(db)
        self.vector_service = VectorService(db, EmbeddingService())
        self.embedding_service = EmbeddingService()
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.OPENAI_API_KEY)

    def get_or_create_conversation(self, user_id: UUID) -> AIConversation:
        """Get or create an AI conversation for a user"""
        conversation = self.ai_repository.get_conversation_by_user_id(user_id)
        if not conversation:
            conversation = AIConversation(user_id=user_id)
            conversation = self.ai_repository.create(conversation)
        return conversation

    def get_conversation_with_messages(
        self,
        conversation_id: UUID,
        limit: int = 50,
        before_message_id: UUID | None = None,
    ) -> AIConversation | None:
        """Get an AI conversation with its messages"""
        return self.ai_repository.get_conversation_with_messages(
            conversation_id, limit, before_message_id
        )

    def create_message(
        self,
        conversation_id: UUID,
        content: str,
        user_id: UUID | None = None,
        parent_id: UUID | None = None,
    ) -> Message:
        """Create a message in an AI conversation"""
        message = Message(
            id=uuid4(),
            content=content,
            user_id=user_id,
            parent_id=parent_id,
            ai_conversation_id=conversation_id,
        )
        return self.ai_repository.create_message(message)

    def analyze_user_style(
        self,
        conversation_id: UUID,
        min_messages: int = 10,
    ) -> str:
        """Analyze user's writing style from past messages"""
        messages = self.vector_service.search_messages(
            query="",
            ai_conversation_ids=[conversation_id],
            limit=min_messages,
        )
        if not messages:
            return "You are a helpful AI assistant."

        # Analyze style and return system message
        return "You are a helpful AI assistant."

    def _stream_ai_response(
        self,
        conversation_id: UUID,
        message: Message,
    ) -> Generator[str, None, None]:
        """Stream AI response for a message"""
        # Create user message
        if not message.content:
            raise ValueError("Message content cannot be empty")

        user_message = self.create_message(
            conversation_id=conversation_id,
            content=message.content,
            user_id=message.user_id,
            parent_id=message.parent_id,
        )

        # Get AI response
        system_message = self.analyze_user_style(conversation_id)

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message.content},
        ]

        stream = self.client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def ai_response_stream(
        self,
        conversation_id: UUID,
        message_text: str,
    ) -> Generator[str, None, None]:
        """Stream AI response for a message"""
        message = Message(
            id=uuid4(),
            content=message_text,
            ai_conversation_id=conversation_id,
        )
        for chunk in self._stream_ai_response(conversation_id, message):
            yield chunk
