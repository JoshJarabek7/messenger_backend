from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlmodel import Session
from unittest.mock import MagicMock, patch

from app.models.domain import AIConversation, Message, User
from app.services.ai_conversation_service import AIConversationService


@pytest.fixture
def test_ai_conversation_in_db(db: Session, test_user_in_db: User) -> AIConversation:
    """Create a test AI conversation in the database."""
    ai_service = AIConversationService(db)
    conversation = ai_service.get_or_create_conversation(test_user_in_db.id)
    return conversation


@pytest.fixture
def test_message_in_db(
    db: Session, test_user_in_db: User, test_ai_conversation_in_db: AIConversation
) -> Message:
    """Create a test message in the database."""
    ai_service = AIConversationService(db)
    message = ai_service.create_message(
        conversation_id=test_ai_conversation_in_db.id,
        content="Test message",
        user_id=test_user_in_db.id,
    )
    return message


@pytest.fixture
def mock_openai_stream():
    """Mock OpenAI API stream response."""
    with (
        patch("openai.resources.chat.completions.Completions.create") as mock_create,
        patch("openai.resources.embeddings.Embeddings.create") as mock_embeddings,
    ):
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Test response"
        mock_create.return_value = [mock_chunk]

        # Mock embeddings response
        mock_embedding_response = MagicMock()
        mock_embedding_response.data = [MagicMock()]
        mock_embedding_response.data[0].embedding = [
            0.1
        ] * 1536  # Standard embedding size
        mock_embeddings.return_value = mock_embedding_response

        yield mock_create


@pytest.mark.asyncio
async def test_get_conversation(
    client: AsyncClient,
    test_user_in_db: User,
    test_ai_conversation_in_db: AIConversation,
):
    """Test getting AI conversation."""
    response = await client.get("/api/ai/conversation")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_ai_conversation_in_db.id)
    assert data["user_id"] == str(test_user_in_db.id)


@pytest.mark.asyncio
async def test_list_conversation_messages(
    client: AsyncClient,
    test_user_in_db: User,
    test_message_in_db: Message,
):
    """Test listing AI conversation messages."""
    response = await client.get("/api/ai/conversation/messages")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == str(test_message_in_db.id)
    assert data[0]["content"] == "Test message"


@pytest.mark.asyncio
async def test_list_conversation_messages_empty(
    client: AsyncClient,
    test_user_in_db: User,
    test_ai_conversation_in_db: AIConversation,
):
    """Test listing AI conversation messages when empty."""
    response = await client.get("/api/ai/conversation/messages")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_create_message(
    client: AsyncClient,
    test_user_in_db: User,
    test_ai_conversation_in_db: AIConversation,
):
    """Test creating a message in AI conversation."""
    response = await client.post(
        "/api/ai/conversation/messages",
        json={
            "content": "Hello AI",
            "parent_id": None,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Hello AI"
    assert data["user_id"] == str(test_user_in_db.id)
    assert data["parent_id"] is None
    assert UUID(data["id"])


@pytest.mark.asyncio
async def test_create_message_with_parent(
    client: AsyncClient,
    test_user_in_db: User,
    test_message_in_db: Message,
):
    """Test creating a message with parent in AI conversation."""
    response = await client.post(
        "/api/ai/conversation/messages",
        json={
            "content": "Reply message",
            "parent_id": str(test_message_in_db.id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Reply message"
    assert data["parent_id"] == str(test_message_in_db.id)
    assert UUID(data["id"])


@pytest.mark.asyncio
async def test_stream_ai_response(
    client: AsyncClient,
    test_user_in_db: User,
    test_ai_conversation_in_db: AIConversation,
    mock_openai_stream,
):
    """Test streaming AI response."""
    response = await client.get(
        "/api/ai/conversation/messages/stream",
        params={"message": "Hello AI"},
    )
    assert response.status_code == 200

    # Read the streamed response
    content = await response.aread()
    text = content.decode()
    assert "Test response" in text
