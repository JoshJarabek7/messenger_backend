from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import Session

from app.models.domain import Message, User, Channel, Workspace
from app.services.message_service import MessageService
from app.repositories.message_repository import MessageRepository
from app.services.workspace_service import WorkspaceService


@pytest.fixture
def test_message_in_db(
    db: Session,
    test_user_in_db: User,
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
) -> Message:
    """Create a test message in the database."""
    message = Message(
        content="Test message",
        user_id=test_user_in_db.id,
        channel_id=test_channel_in_db.id,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    # Set relationships for testing
    message.channel = test_channel_in_db
    test_channel_in_db.workspace = test_workspace_in_db

    return message


@pytest.mark.asyncio
async def test_get_message(client: AsyncClient, test_message_in_db: Message):
    """Test getting a specific message."""
    response = await client.get(f"/api/messages/{test_message_in_db.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_message_in_db.id)
    assert data["content"] == test_message_in_db.content


@pytest.mark.asyncio
async def test_get_message_not_found(client: AsyncClient):
    """Test getting a non-existent message."""
    response = await client.get(f"/api/messages/{UUID(int=0)}")
    assert response.status_code == 404
    assert "message not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_message(client: AsyncClient, test_message_in_db: Message):
    """Test deleting a message."""
    response = await client.delete(f"/api/messages/{test_message_in_db.id}")
    assert response.status_code == 200
    assert response.json()["message"] == "Message deleted successfully"

    # Verify message is deleted
    response = await client.get(f"/api/messages/{test_message_in_db.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_message_not_found(client: AsyncClient):
    """Test deleting a non-existent message."""
    response = await client.delete(f"/api/messages/{UUID(int=0)}")
    assert response.status_code == 404
    assert "message not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_message_unauthorized(
    client: AsyncClient,
    test_message_in_db: Message,
    test_other_user_in_db: User,
):
    """Test deleting someone else's message."""
    # Change message owner to other user
    test_message_in_db.user_id = test_other_user_in_db.id

    response = await client.delete(f"/api/messages/{test_message_in_db.id}")
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_add_reaction(client: AsyncClient, test_message_in_db: Message):
    """Test adding a reaction to a message."""
    response = await client.post(
        f"/api/messages/{test_message_in_db.id}/reactions",
        json={
            "reaction_type": "👍",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["emoji"] == "👍"
    assert UUID(data["id"])
    assert data["message_id"] == str(test_message_in_db.id)


@pytest.mark.asyncio
async def test_remove_reaction(
    client: AsyncClient,
    test_message_in_db: Message,
    test_user_in_db: User,
    db: Session,
):
    """Test removing a reaction from a message."""
    # Add reaction first
    message_service = MessageService(MessageRepository(db))
    reaction = message_service.add_reaction(
        message_id=test_message_in_db.id,
        user_id=test_user_in_db.id,
        emoji="👍",
    )

    # Remove reaction
    response = await client.delete(
        f"/api/messages/{test_message_in_db.id}/reactions/{reaction.id}"
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Reaction removed successfully"


@pytest.mark.asyncio
async def test_remove_reaction_message_not_found(client: AsyncClient):
    """Test removing a reaction from a non-existent message."""
    response = await client.delete(
        f"/api/messages/{UUID(int=0)}/reactions/{UUID(int=0)}"
    )
    assert response.status_code == 404
    assert "message not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_remove_reaction_not_found(
    client: AsyncClient,
    test_message_in_db: Message,
):
    """Test removing a non-existent reaction."""
    response = await client.delete(
        f"/api/messages/{test_message_in_db.id}/reactions/{UUID(int=0)}"
    )
    assert response.status_code == 404
    assert "reaction not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_remove_reaction_unauthorized(
    client: AsyncClient,
    test_message_in_db: Message,
    test_user_in_db: User,
    test_other_user_in_db: User,
    db: Session,
):
    """Test removing someone else's reaction."""
    # Add reaction as other user
    message_service = MessageService(MessageRepository(db))
    reaction = message_service.add_reaction(
        message_id=test_message_in_db.id,
        user_id=test_other_user_in_db.id,
        emoji="👍",
    )

    # Try to remove reaction as current user
    response = await client.delete(
        f"/api/messages/{test_message_in_db.id}/reactions/{reaction.id}"
    )
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_thread(
    client: AsyncClient,
    test_message_in_db: Message,
    test_user_in_db: User,
    db: Session,
):
    """Test getting a message thread."""
    # Create a reply first
    message_service = MessageService(MessageRepository(db))
    reply = Message(
        content="Reply message",
        user_id=test_user_in_db.id,
        channel_id=test_message_in_db.channel_id,
        parent_id=test_message_in_db.id,
    )
    db.add(reply)
    db.commit()

    response = await client.get(f"/api/messages/{test_message_in_db.id}/thread")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2  # Original message + reply
    assert any(msg["content"] == "Reply message" for msg in data)
