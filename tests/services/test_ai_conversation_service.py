from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4
from unittest.mock import MagicMock, patch

import pytest
import openai_responses
from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.completion_usage import CompletionUsage
from sqlmodel import Session

from app.models.domain import AIConversation, Message, User
from app.services.ai_conversation_service import AIConversationService


@pytest.fixture
def mock_openai_response():
    return ChatCompletion(
        id="chatcmpl-123",
        choices=[
            Choice(
                finish_reason="stop",
                index=0,
                message=ChatCompletionMessage(
                    content="Test response",
                    role="assistant",
                ),
                logprobs=None,
            )
        ],
        created=1677858242,
        model="gpt-4",
        object="chat.completion",
        usage=CompletionUsage(completion_tokens=50, prompt_tokens=50, total_tokens=100),
        system_fingerprint=None,
    )


@pytest.fixture
def mock_openai_stream():
    class StreamIterator:
        def __init__(self):
            self.chunks = [
                MagicMock(choices=[MagicMock(delta=MagicMock(content="Test "))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content="response"))]),
                MagicMock(
                    choices=[
                        MagicMock(delta=MagicMock(content=None), finish_reason="stop")
                    ]
                ),
            ]
            self.index = 0

        def __iter__(self):
            return self

        def __next__(self):
            if self.index >= len(self.chunks):
                raise StopIteration
            chunk = self.chunks[self.index]
            self.index += 1
            return chunk

    return StreamIterator()


@pytest.fixture
def mock_openai():
    """Mock OpenAI client with proper response structure."""
    with patch("openai.OpenAI") as mock:
        mock_instance = MagicMock()
        mock_instance.chat.completions.create.return_value = MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(content="Test response"), finish_reason="stop"
                )
            ]
        )
        mock_instance.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )
        mock.return_value = mock_instance
        return mock_instance


@pytest.fixture
def mock_vector_service(mocker):
    """Mock vector service."""
    mock = mocker.Mock()
    mock.search_messages.return_value = []
    mock.index_message = mocker.AsyncMock()
    return mock


@pytest.fixture
def service(db: Session, mock_openai, mock_vector_service, mocker):
    """Create service with mocked dependencies."""
    mocker.patch(
        "app.services.ai_conversation_service.VectorService",
        return_value=mock_vector_service,
    )
    return AIConversationService(db)


def test_get_or_create_conversation(db: Session, test_user_in_db: User):
    service = AIConversationService(db)
    conversation = service.get_or_create_conversation(test_user_in_db.id)

    assert isinstance(conversation, AIConversation)
    assert conversation.user_id == test_user_in_db.id


def test_create_message(db: Session, test_user_in_db: User):
    service = AIConversationService(db)
    conversation = service.get_or_create_conversation(test_user_in_db.id)

    created_message = service.create_message(
        conversation_id=conversation.id,
        content="Hello AI",
        user_id=test_user_in_db.id,
    )
    assert created_message.content == "Hello AI"
    assert created_message.user_id == test_user_in_db.id


def test_get_conversation_with_messages(db: Session, test_user_in_db: User):
    service = AIConversationService(db)
    conversation = service.get_or_create_conversation(test_user_in_db.id)

    # Add a message
    message = service.create_message(
        conversation_id=conversation.id,
        content="Hello AI",
        user_id=test_user_in_db.id,
    )

    # Get conversation with messages
    conv_with_messages = service.get_conversation_with_messages(conversation.id)
    assert conv_with_messages is not None
    assert len(conv_with_messages.messages) == 1
    assert conv_with_messages.messages[0].content == "Hello AI"
    assert conv_with_messages.messages[0].id == message.id

    # Test with before_message_id
    conv_with_messages = service.get_conversation_with_messages(
        conversation.id, before_message_id=message.id
    )
    assert conv_with_messages is not None
    assert len(conv_with_messages.messages) == 0


@pytest.mark.asyncio
async def test_ai_response_stream(
    service: AIConversationService, test_user_in_db: User, mocker
):
    """Test streaming response."""
    conversation = service.get_or_create_conversation(test_user_in_db.id)

    # Mock OpenAI chat completion stream
    mock_stream = mocker.MagicMock()
    mock_stream.__iter__ = mocker.MagicMock(
        return_value=iter(
            [
                mocker.MagicMock(
                    choices=[mocker.MagicMock(delta=mocker.MagicMock(content="Test "))]
                ),
                mocker.MagicMock(
                    choices=[
                        mocker.MagicMock(delta=mocker.MagicMock(content="response"))
                    ]
                ),
                mocker.MagicMock(
                    choices=[
                        mocker.MagicMock(
                            delta=mocker.MagicMock(content=None), finish_reason="stop"
                        )
                    ]
                ),
            ]
        )
    )

    # Mock the create method
    mock_create = mocker.MagicMock(return_value=mock_stream)
    mocker.patch.object(service.client.chat.completions, "create", mock_create)

    # Test streaming response
    chunks = []
    for chunk in service.ai_response_stream(conversation.id, "Hello AI"):
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0] == "Test "
    assert chunks[1] == "response"


@pytest.mark.asyncio
async def test_analyze_user_style_no_messages(
    service: AIConversationService, test_user_in_db: User
):
    """Test analyzing user style with no messages."""
    conversation = service.get_or_create_conversation(test_user_in_db.id)

    style = service.analyze_user_style(conversation.id)
    assert style == "You are a helpful AI assistant."


@pytest.mark.asyncio
async def test_analyze_user_style_with_messages(
    service: AIConversationService, test_user_in_db: User
):
    """Test analyzing user style with existing messages."""
    conversation = service.get_or_create_conversation(test_user_in_db.id)

    # Add some messages
    for i in range(5):
        service.create_message(
            conversation_id=conversation.id,
            content=f"Test message {i}",
            user_id=test_user_in_db.id,
        )

    style = service.analyze_user_style(conversation.id)
    assert style == "You are a helpful AI assistant."
