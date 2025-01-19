from datetime import UTC, datetime
from typing import Any, AsyncGenerator, Dict, List, cast
from unittest.mock import MagicMock
from uuid import UUID
import asyncio

import pytest
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta
from sqlmodel import Session
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocket, WebSocketState

from app.core.events import Event, EventType
from app.core.websocket import WebSocketManager
from app.models.domain import User
from app.models.schemas.events import (
    AIError,
    AIMessageChunk,
    BaseWebSocketMessage,
    Heartbeat,
    HeartbeatResponse,
    InboundMessage,
    InboundMessageContent,
    MessageContent,
    ReadStatus,
    TypingStatus,
    UserStatus,
)

from tests.conftest import MockWebSocket


@pytest.fixture
def mock_websocket() -> MockWebSocket:
    return MockWebSocket()


@pytest.fixture
def websocket_manager() -> WebSocketManager:
    manager = WebSocketManager()
    # Clear any existing connections
    manager._connections = {}
    manager._typing_status = {}
    return manager


@pytest.mark.asyncio
async def test_connect_and_disconnect(
    websocket_manager: WebSocketManager, mock_websocket: MockWebSocket
):
    """Test connection and disconnection handling."""
    user_id = UUID("12345678-1234-5678-1234-567812345678")

    # Test connect
    await websocket_manager.connect(mock_websocket, user_id)
    assert mock_websocket._connected
    assert user_id in websocket_manager._connections
    assert websocket_manager.is_user_online(user_id)
    assert user_id in websocket_manager.get_online_users()

    # Test disconnect
    await websocket_manager.disconnect(user_id)
    assert not mock_websocket._connected
    assert user_id not in websocket_manager._connections
    assert not websocket_manager.is_user_online(user_id)
    assert user_id not in websocket_manager.get_online_users()


@pytest.mark.asyncio
async def test_send_personal_message(
    websocket_manager: WebSocketManager, mock_websocket: MockWebSocket
):
    """Test sending personal messages."""
    user_id = UUID("12345678-1234-5678-1234-567812345678")
    await websocket_manager.connect(mock_websocket, user_id)

    # Test valid message
    message = UserStatus(
        type=EventType.USER_ONLINE,
        data={"user_id": str(user_id), "is_online": True},
        user_id=user_id,
    )
    await websocket_manager.send_personal_message(user_id, message)
    assert len(mock_websocket.sent_messages) == 1
    assert mock_websocket.sent_messages[0]["type"] == EventType.USER_ONLINE

    # Test message to non-existent user
    non_existent_user = UUID("87654321-4321-8765-4321-876543210987")
    await websocket_manager.send_personal_message(non_existent_user, message)
    assert len(mock_websocket.sent_messages) == 1  # No new messages


@pytest.mark.asyncio
async def test_broadcast(websocket_manager: WebSocketManager):
    """Test broadcasting messages."""
    # Setup multiple connections
    user1_id = UUID("12345678-1234-5678-1234-567812345678")
    user2_id = UUID("87654321-4321-8765-4321-876543210987")
    user3_id = UUID("11111111-2222-3333-4444-555555555555")

    mock1 = MockWebSocket()
    mock2 = MockWebSocket()
    mock3 = MockWebSocket()

    await websocket_manager.connect(mock1, user1_id)
    await websocket_manager.connect(mock2, user2_id)
    await websocket_manager.connect(mock3, user3_id)

    message = UserStatus(
        type=EventType.USER_ONLINE,
        data={"user_id": str(user1_id), "is_online": True},
        user_id=user1_id,
    )

    # Test broadcast to all
    await websocket_manager.broadcast(message)
    assert len(mock1.sent_messages) == 1
    assert len(mock2.sent_messages) == 1
    assert len(mock3.sent_messages) == 1

    # Test broadcast with exclusion
    await websocket_manager.broadcast(message, exclude={user1_id, user2_id})
    assert len(mock1.sent_messages) == 1  # No new message
    assert len(mock2.sent_messages) == 1  # No new message
    assert len(mock3.sent_messages) == 2  # Got new message


@pytest.mark.asyncio
async def test_handle_client_message(
    websocket_manager: WebSocketManager, mock_websocket: MockWebSocket
):
    """Test client message handling."""
    user_id = UUID("12345678-1234-5678-1234-567812345678")
    await websocket_manager.connect(mock_websocket, user_id)

    # Test heartbeat
    ping_message = {"type": "ping"}
    await websocket_manager.handle_client_message(user_id, ping_message)
    assert mock_websocket.sent_messages[-1]["type"] == "pong"

    # Test invalid message type
    invalid_message = {"type": "invalid_type"}
    await websocket_manager.handle_client_message(user_id, invalid_message)
    assert mock_websocket.sent_messages[-1]["type"] == EventType.AI_ERROR

    # Test missing type
    missing_type = {"data": "some data"}
    await websocket_manager.handle_client_message(user_id, missing_type)
    assert mock_websocket.sent_messages[-1]["type"] == EventType.AI_ERROR


@pytest.mark.asyncio
async def test_stream_ai_response(
    websocket_manager: WebSocketManager, mock_websocket: MockWebSocket
):
    """Test AI response streaming."""
    user_id = UUID("12345678-1234-5678-1234-567812345678")
    message_id = UUID("12345678-1234-5678-1234-567812345678")
    await websocket_manager.connect(mock_websocket, user_id)

    async def mock_stream() -> AsyncGenerator[ChatCompletionChunk, None]:
        yield ChatCompletionChunk(
            id="1",
            choices=[
                Choice(
                    delta=ChoiceDelta(content="Hello ", role=None, tool_calls=None),
                    finish_reason=None,
                    index=0,
                )
            ],
            created=1234567890,
            model="gpt-4",
            object="chat.completion.chunk",
        )
        yield ChatCompletionChunk(
            id="2",
            choices=[
                Choice(
                    delta=ChoiceDelta(content="world!", role=None, tool_calls=None),
                    finish_reason=None,
                    index=0,
                )
            ],
            created=1234567890,
            model="gpt-4",
            object="chat.completion.chunk",
        )

    await websocket_manager.stream_ai_response(user_id, mock_stream(), message_id)

    # Verify chunks were sent
    assert len(mock_websocket.sent_messages) == 2
    assert mock_websocket.sent_messages[0]["data"]["content"] == "Hello "
    assert mock_websocket.sent_messages[1]["data"]["content"] == "world!"


@pytest.mark.asyncio
async def test_handle_event(
    websocket_manager: WebSocketManager, mock_websocket: MockWebSocket
):
    """Test event handling."""
    user_id = UUID("12345678-1234-5678-1234-567812345678")
    await websocket_manager.connect(mock_websocket, user_id)

    event = Event(
        type=EventType.USER_ONLINE,
        data={"user_id": str(user_id), "is_online": True},
        user_id=user_id,
    )
    await websocket_manager._handle_event(event)
    assert len(mock_websocket.sent_messages) > 0
    assert mock_websocket.sent_messages[-1]["type"] == EventType.USER_ONLINE


@pytest.mark.asyncio
async def test_update_typing_status(
    websocket_manager: WebSocketManager, mock_websocket: MockWebSocket
):
    """Test typing status updates."""
    user_id = UUID("12345678-1234-5678-1234-567812345678")
    conversation_id = UUID("87654321-4321-8765-4321-876543210987")
    await websocket_manager.connect(mock_websocket, user_id)

    # Test typing started
    await websocket_manager.update_typing_status(conversation_id, user_id, True)
    assert user_id in websocket_manager._typing_status[conversation_id]
    assert mock_websocket.sent_messages[-1]["type"] == EventType.TYPING_STARTED

    # Test typing stopped
    await websocket_manager.update_typing_status(conversation_id, user_id, False)
    assert user_id not in websocket_manager._typing_status[conversation_id]
    assert mock_websocket.sent_messages[-1]["type"] == EventType.TYPING_STOPPED

    # Test disconnection removes from typing status
    await websocket_manager.update_typing_status(conversation_id, user_id, True)
    await websocket_manager.disconnect(user_id)
    assert user_id not in websocket_manager._typing_status[conversation_id]


@pytest.mark.asyncio
async def test_update_read_status(
    websocket_manager: WebSocketManager, mock_websocket: MockWebSocket
):
    """Test read status updates."""
    user_id = UUID("12345678-1234-5678-1234-567812345678")
    conversation_id = UUID("87654321-4321-8765-4321-876543210987")
    message_id = UUID("11111111-2222-3333-4444-555555555555")
    await websocket_manager.connect(mock_websocket, user_id)

    status = ReadStatus(
        type=EventType.READ_STATUS_UPDATED,
        data={"last_read_message_id": str(message_id)},
        conversation_id=conversation_id,
        user_id=user_id,
    )
    await websocket_manager.update_read_status(status)
    assert mock_websocket.sent_messages[-1]["type"] == EventType.READ_STATUS_UPDATED
    assert mock_websocket.sent_messages[-1]["data"]["conversation_id"] == str(
        conversation_id
    )
    assert mock_websocket.sent_messages[-1]["data"]["last_read_message_id"] == str(
        message_id
    )


@pytest.mark.asyncio
async def test_handle_new_message(
    websocket_manager: WebSocketManager, mock_websocket: MockWebSocket
):
    """Test handling of new messages."""
    user_id = UUID("12345678-1234-5678-1234-567812345678")
    workspace_id = UUID("87654321-4321-8765-4321-876543210987")
    channel_id = UUID("11111111-2222-3333-4444-555555555555")
    await websocket_manager.connect(mock_websocket, user_id)

    message = InboundMessage(
        type=EventType.MESSAGE_CREATED,
        data=InboundMessageContent(
            content="Test message",
            parent_id=None,
        ),
        workspace_id=workspace_id,
        channel_id=channel_id,
    )
    await websocket_manager.handle_new_message(user_id, message)
    assert mock_websocket.sent_messages[-1]["type"] == EventType.MESSAGE_CREATED
    assert mock_websocket.sent_messages[-1]["data"]["content"] == "Test message"
