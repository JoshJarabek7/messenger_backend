from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import Session
from fastapi import FastAPI

from app.models.domain import DirectMessageConversation, Message, User
from app.services.direct_message_service import DirectMessageService
from app.repositories.direct_message_repository import DirectMessageRepository
from app.services.user_service import UserService
from app.api.dependencies import get_current_user
from tests.conftest import (
    TEST_USER_DISPLAY_NAME,
    TEST_USER_EMAIL,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)
from typing import Callable, Awaitable, Any
from loguru import logger


@pytest.fixture
def test_unauthorized_user_in_db(db: Session) -> User:
    """Create an unauthorized test user in the database."""
    user_service = UserService(db)
    return user_service.create_user(
        email="unauthorized@example.com",
        password="testpassword123",
        username="unauthorized",
        display_name="Unauthorized User",
    )


@pytest.fixture
def test_dm_conversation_in_db(
    db: Session, test_user_in_db: User, test_other_user_in_db: User
) -> DirectMessageConversation:
    """Create a test DM conversation in the database."""
    dm_service = DirectMessageService(DirectMessageRepository(db))
    conversation = dm_service.get_or_create_conversation(
        user1_id=test_user_in_db.id,
        user2_id=test_other_user_in_db.id,
    )
    return conversation


@pytest.mark.asyncio
async def test_list_conversations(
    client: AsyncClient, test_dm_conversation_in_db: DirectMessageConversation
):
    """Test listing DM conversations."""
    response = await client.get("/api/dm/conversations")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(conv["id"] == str(test_dm_conversation_in_db.id) for conv in data)


@pytest.mark.asyncio
async def test_create_conversation(
    client: AsyncClient, test_user_in_db: User, test_other_user_in_db: User
):
    """Test creating a new DM conversation."""
    response = await client.post(
        "/api/dm/conversations",
        json={
            "user_id": str(test_other_user_in_db.id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert UUID(data["id"])
    assert data["user1_id"] in [str(test_user_in_db.id), str(test_other_user_in_db.id)]
    assert data["user2_id"] in [str(test_user_in_db.id), str(test_other_user_in_db.id)]


@pytest.mark.asyncio
async def test_get_conversation(
    client: AsyncClient,
    test_dm_conversation_in_db: DirectMessageConversation,
):
    """Test getting a specific DM conversation."""
    response = await client.get(
        f"/api/dm/conversations/{test_dm_conversation_in_db.id}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_dm_conversation_in_db.id)


@pytest.mark.asyncio
async def test_get_conversation_not_found(client: AsyncClient):
    """Test getting a non-existent DM conversation."""
    response = await client.get(f"/api/dm/conversations/{UUID(int=0)}")
    assert response.status_code == 404
    assert "conversation not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_conversation_unauthorized(
    make_client: Callable[[dict[str, Any] | None], Awaitable[AsyncClient]],
    test_dm_conversation_in_db: DirectMessageConversation,
    test_unauthorized_user_in_db: User,
    test_app: FastAPI,
    db: Session,
):
    """Test getting a DM conversation without authorization."""
    # Ensure both users are attached to the session
    db.refresh(test_unauthorized_user_in_db)
    db.refresh(test_dm_conversation_in_db)

    # Override get_current_user to return the unauthorized user
    async def override_get_current_user():
        return test_unauthorized_user_in_db

    test_app.dependency_overrides[get_current_user] = override_get_current_user
    other_client = await make_client(
        {"Authorization": f"Bearer {test_unauthorized_user_in_db.id}"}
    )

    response = await other_client.get(
        f"/api/dm/conversations/{test_dm_conversation_in_db.id}"
    )
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_conversation_messages(
    client: AsyncClient,
    test_dm_conversation_in_db: DirectMessageConversation,
    test_user_in_db: User,
    db: Session,
):
    """Test listing messages in a DM conversation."""
    # Create a test message first
    dm_service = DirectMessageService(DirectMessageRepository(db))
    message = Message(
        id=uuid4(),
        content="Test message",
        user_id=test_user_in_db.id,
    )
    dm_service.create_message(test_dm_conversation_in_db.id, message)

    response = await client.get(
        f"/api/dm/conversations/{test_dm_conversation_in_db.id}/messages"
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["content"] == "Test message"


@pytest.mark.asyncio
async def test_list_conversation_messages_not_found(client: AsyncClient):
    """Test listing messages in a non-existent DM conversation."""
    response = await client.get(f"/api/dm/conversations/{UUID(int=0)}/messages")
    assert response.status_code == 404
    assert "conversation not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_conversation_messages_unauthorized(
    make_client: Callable[[dict[str, Any] | None], Awaitable[AsyncClient]],
    test_dm_conversation_in_db: DirectMessageConversation,
    test_unauthorized_user_in_db: User,
    test_app: FastAPI,
    db: Session,
):
    """Test listing messages in a DM conversation without authorization."""
    # Ensure both users are attached to the session
    db.refresh(test_unauthorized_user_in_db)
    db.refresh(test_dm_conversation_in_db)

    # Override get_current_user to return the unauthorized user
    async def override_get_current_user():
        return test_unauthorized_user_in_db

    test_app.dependency_overrides[get_current_user] = override_get_current_user
    other_client = await make_client(
        {"Authorization": f"Bearer {test_unauthorized_user_in_db.id}"}
    )

    response = await other_client.get(
        f"/api/dm/conversations/{test_dm_conversation_in_db.id}/messages"
    )
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_conversation_message(
    client: AsyncClient,
    test_dm_conversation_in_db: DirectMessageConversation,
):
    """Test creating a message in a DM conversation."""
    response = await client.post(
        f"/api/dm/conversations/{test_dm_conversation_in_db.id}/messages",
        json={
            "content": "Test message",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Test message"
    assert UUID(data["id"])


@pytest.mark.asyncio
async def test_create_conversation_message_with_parent(
    client: AsyncClient,
    test_dm_conversation_in_db: DirectMessageConversation,
):
    """Test creating a reply message in a DM conversation."""
    # Create parent message first
    parent_response = await client.post(
        f"/api/dm/conversations/{test_dm_conversation_in_db.id}/messages",
        json={
            "content": "Parent message",
        },
    )
    assert parent_response.status_code == 200
    parent_id = parent_response.json()["id"]

    # Create reply
    response = await client.post(
        f"/api/dm/conversations/{test_dm_conversation_in_db.id}/messages",
        json={
            "content": "Reply message",
            "parent_id": parent_id,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Reply message"
    assert data["parent_id"] == parent_id
