from typing import Any, cast
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect
from sqlmodel import Session

from app.api.routes.websocket import get_ws_user, websocket_endpoint
from app.core.events import EventType
from app.core.websocket import WebSocketManager
from app.models.domain import User
from app.services.ai_conversation_service import AIConversationService
from tests.core.test_websocket_manager import MockWebSocket


@pytest.fixture
def mock_websocket() -> MockWebSocket:
    return MockWebSocket()


@pytest.mark.asyncio
async def test_websocket_endpoint_normal_message(
    mock_websocket: MockWebSocket,
    test_user_in_db: User,
    db: Session,
):
    """Test websocket endpoint with normal message handling."""
    # Override receive_json to send a normal message then disconnect
    message_id = uuid4()
    channel_id = uuid4()
    message_sent = False

    async def mock_receive_json() -> dict[str, Any]:
        nonlocal message_sent
        if not message_sent:
            message_sent = True
            return {
                "type": "message_created",
                "data": {
                    "content": "Test message",
                    "parent_id": None,
                },
                "channel_id": str(channel_id),
                "message_id": str(message_id),
            }
        raise WebSocketDisconnect(code=1000)

    mock_websocket.receive_json = mock_receive_json  # type: ignore

    # Call the endpoint
    with patch.object(WebSocketManager, "handle_client_message") as mock_handle:
        await websocket_endpoint(mock_websocket, test_user_in_db, db)

        # Verify handle_client_message was called with correct args
        mock_handle.assert_called_once()
        call_args = mock_handle.call_args[0]
        assert call_args[0] == test_user_in_db.id
        assert call_args[1]["type"] == "message_created"
        assert call_args[1]["data"]["content"] == "Test message"


@pytest.mark.asyncio
async def test_websocket_endpoint_ai_message(
    mock_websocket: MockWebSocket,
    test_user_in_db: User,
    db: Session,
):
    """Test websocket endpoint with AI message handling."""
    message_id = uuid4()
    ai_conversation_id = uuid4()
    message_sent = False

    # Override receive_json to send an AI message then disconnect
    async def mock_receive_json() -> dict[str, Any]:
        nonlocal message_sent
        if not message_sent:
            message_sent = True
            return {
                "type": "message_created",
                "ai_conversation_id": str(ai_conversation_id),
                "content": "Test message",
                "message_id": str(message_id),
            }
        mock_websocket._should_disconnect = True
        raise WebSocketDisconnect(code=1000)

    mock_websocket.receive_json = mock_receive_json  # type: ignore

    # Mock AI conversation service
    mock_conversation = MagicMock()
    mock_conversation.id = ai_conversation_id

    # Create a proper async generator for the AI response stream
    async def mock_stream():
        yield MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))])
        yield MagicMock(choices=[MagicMock(delta=MagicMock(content="world"))])
        yield MagicMock(
            choices=[MagicMock(delta=MagicMock(content=None), finish_reason="stop")]
        )

    with (
        patch.object(
            AIConversationService,
            "get_or_create_conversation",
            return_value=mock_conversation,
        ),
        patch.object(
            AIConversationService,
            "ai_response_stream",
            return_value=mock_stream(),
        ),
    ):
        await websocket_endpoint(mock_websocket, test_user_in_db, db)

    # Verify AI message chunks were sent
    ai_chunks = [
        msg for msg in mock_websocket.sent_messages if msg["type"] == "ai_message_chunk"
    ]
    assert len(ai_chunks) == 2
    assert ai_chunks[0]["data"]["content"] == "Hello"
    assert ai_chunks[1]["data"]["content"] == "world"
    assert all(chunk["data"]["message_id"] == str(message_id) for chunk in ai_chunks)


@pytest.mark.asyncio
async def test_websocket_endpoint_error_handling(
    mock_websocket: MockWebSocket,
    test_user_in_db: User,
    db: Session,
):
    """Test websocket endpoint error handling."""
    error_sent = False

    # Override receive_json to raise an error then disconnect
    async def mock_receive_json() -> dict[str, Any]:
        nonlocal error_sent
        if not error_sent:
            error_sent = True
            raise ValueError("Test error")
        mock_websocket._should_disconnect = True
        raise WebSocketDisconnect(code=1000)

    mock_websocket.receive_json = mock_receive_json  # type: ignore

    await websocket_endpoint(mock_websocket, test_user_in_db, db)

    # Verify error message was sent
    error_messages = [
        msg for msg in mock_websocket.sent_messages if msg["type"] == EventType.AI_ERROR
    ]
    assert len(error_messages) == 1
    assert error_messages[0]["data"]["error"] == "Error processing message"
    assert "Test error" in error_messages[0]["data"]["details"]


@pytest.mark.asyncio
async def test_websocket_endpoint_no_token(
    mock_websocket: MockWebSocket,
    db: Session,
):
    """Test websocket endpoint with no access token."""
    # Clear any existing cookies
    mock_websocket.cookies = {}

    with pytest.raises(WebSocketDisconnect) as exc_info:
        user = await get_ws_user(mock_websocket, db)
        await websocket_endpoint(mock_websocket, user, db)
    assert exc_info.value.code == 1008
    assert exc_info.value.reason == "No access token cookie provided"


@pytest.mark.asyncio
async def test_websocket_endpoint_invalid_token(
    mock_websocket: MockWebSocket,
    db: Session,
):
    """Test websocket endpoint with invalid token."""
    mock_websocket.cookies = {"access_token": "invalid_token"}

    with pytest.raises(WebSocketDisconnect) as exc_info:
        user = await get_ws_user(mock_websocket, db)
        await websocket_endpoint(mock_websocket, user, db)
    assert exc_info.value.code == 1008
    assert exc_info.value.reason == "Invalid token"
