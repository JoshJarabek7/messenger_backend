from uuid import UUID
from typing import Any, Callable, Awaitable

import pytest
from httpx import AsyncClient
from sqlmodel import Session
from fastapi import FastAPI

from app.models.domain import Channel, User, Workspace, WorkspaceMember
from app.models.types.workspace_role import WorkspaceRole
from app.services.workspace_service import WorkspaceService
from app.api.dependencies import get_current_user
from tests.conftest import (
    TEST_USER_DISPLAY_NAME,
    TEST_USER_EMAIL,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)


@pytest.fixture
def test_workspace_in_db(db: Session, test_user_in_db: User) -> Workspace:
    """Create a test workspace in the database."""
    workspace_service = WorkspaceService(db)
    return workspace_service.create_workspace(
        name="Test Workspace",
        description="Test workspace description",
        created_by_id=test_user_in_db.id,
    )


@pytest.fixture
def test_channel_in_db(
    db: Session, test_workspace_in_db: Workspace, test_user_in_db: User
) -> Channel:
    """Create a test channel in the database."""
    workspace_service = WorkspaceService(db)
    return workspace_service.create_channel(
        workspace_id=test_workspace_in_db.id,
        name="test-channel",
        description="Test channel",
        created_by_id=test_user_in_db.id,
    )


@pytest.mark.asyncio
async def test_list_channels(
    client: AsyncClient, test_workspace_in_db: Workspace, test_channel_in_db: Channel
):
    """Test listing channels in a workspace."""
    response = await client.get(f"/api/workspaces/{test_workspace_in_db.id}/channels")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1  # Should have at least the general channel
    assert any(channel["name"] == "test-channel" for channel in data)


@pytest.mark.asyncio
async def test_list_channels_unauthorized(
    make_client: Callable[[dict[str, Any] | None], Awaitable[AsyncClient]],
    test_workspace_in_db: Workspace,
    test_other_user_in_db: User,
    test_app: FastAPI,
    db: Session,
):
    """Test listing channels without proper permissions."""
    # Ensure user is attached to the session
    db.refresh(test_other_user_in_db)

    # Override get_current_user to return the unauthorized user
    async def override_get_current_user():
        return test_other_user_in_db

    test_app.dependency_overrides[get_current_user] = override_get_current_user

    # Create a new client for the other user
    other_client = await make_client(
        {"Authorization": f"Bearer {test_other_user_in_db.id}"}
    )

    # Remove test_other_user from workspace
    workspace_service = WorkspaceService(db)
    workspace_service.remove_member(test_workspace_in_db.id, test_other_user_in_db.id)

    # Try to list channels as other user
    response = await other_client.get(
        f"/api/workspaces/{test_workspace_in_db.id}/channels"
    )
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_channel(client: AsyncClient, test_workspace_in_db: Workspace):
    """Test creating a new channel."""
    response = await client.post(
        f"/api/workspaces/{test_workspace_in_db.id}/channels",
        json={
            "name": "new-channel",
            "description": "A new test channel",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "new-channel"
    assert data["description"] == "A new test channel"
    assert UUID(data["id"])


@pytest.mark.asyncio
async def test_create_channel_unauthorized(
    make_client: Callable[[dict[str, Any] | None], Awaitable[AsyncClient]],
    test_workspace_in_db: Workspace,
    test_other_user_in_db: User,
    test_app: FastAPI,
    db: Session,
):
    """Test creating a channel without proper permissions."""
    # Ensure user is attached to the session
    db.refresh(test_other_user_in_db)

    # Override get_current_user to return the unauthorized user
    async def override_get_current_user():
        return test_other_user_in_db

    test_app.dependency_overrides[get_current_user] = override_get_current_user

    # Create a new client for the other user
    other_client = await make_client(
        {"Authorization": f"Bearer {test_other_user_in_db.id}"}
    )

    # Add test_other_user as member (not admin/owner)
    workspace_service = WorkspaceService(db)
    workspace_service.add_member(
        workspace_id=test_workspace_in_db.id,
        user_id=test_other_user_in_db.id,
        role=WorkspaceRole.MEMBER,
    )

    response = await other_client.post(
        f"/api/workspaces/{test_workspace_in_db.id}/channels",
        json={
            "name": "unauthorized-channel",
            "description": "This should fail",
        },
    )
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_channel(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
):
    """Test getting a specific channel."""
    response = await client.get(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/{test_channel_in_db.slug}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_channel_in_db.id)
    assert data["name"] == test_channel_in_db.name


@pytest.mark.asyncio
async def test_get_channel_not_found(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
):
    """Test getting a non-existent channel."""
    response = await client.get(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/non-existent"
    )
    assert response.status_code == 404
    assert "channel not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_channel(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
):
    """Test updating a channel."""
    response = await client.put(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/{test_channel_in_db.slug}",
        json={
            "name": "updated-channel",
            "description": "Updated description",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "updated-channel"
    assert data["description"] == "Updated description"


@pytest.mark.asyncio
async def test_update_channel_not_found(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
):
    """Test updating a non-existent channel."""
    response = await client.put(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/non-existent",
        json={
            "name": "updated-channel",
            "description": "Updated description",
        },
    )
    assert response.status_code == 404
    assert "channel not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_channel_unauthorized(
    make_client: Callable[[dict[str, Any] | None], Awaitable[AsyncClient]],
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
    test_other_user_in_db: User,
    test_app: FastAPI,
    db: Session,
):
    """Test updating a channel without proper permissions."""
    # Ensure user is attached to the session
    db.refresh(test_other_user_in_db)

    # Override get_current_user to return the unauthorized user
    async def override_get_current_user():
        return test_other_user_in_db

    test_app.dependency_overrides[get_current_user] = override_get_current_user

    # Create a new client for the other user
    other_client = await make_client(
        {"Authorization": f"Bearer {test_other_user_in_db.id}"}
    )

    # Add test_other_user as member (not admin/owner)
    workspace_service = WorkspaceService(db)
    workspace_service.add_member(
        workspace_id=test_workspace_in_db.id,
        user_id=test_other_user_in_db.id,
        role=WorkspaceRole.MEMBER,
    )

    response = await other_client.put(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/{test_channel_in_db.slug}",
        json={
            "name": "unauthorized-update",
            "description": "This should fail",
        },
    )
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_channel(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
):
    """Test deleting a channel."""
    response = await client.delete(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/{test_channel_in_db.slug}"
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Channel deleted successfully"

    # Verify channel is deleted
    response = await client.get(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/{test_channel_in_db.slug}"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_channel_not_found(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
):
    """Test deleting a non-existent channel."""
    response = await client.delete(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/non-existent"
    )
    assert response.status_code == 404
    assert "channel not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_channel_unauthorized(
    make_client: Callable[[dict[str, Any] | None], Awaitable[AsyncClient]],
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
    test_other_user_in_db: User,
    test_app: FastAPI,
    db: Session,
):
    """Test deleting a channel without proper permissions."""
    # Ensure user is attached to the session
    db.refresh(test_other_user_in_db)

    # Override get_current_user to return the unauthorized user
    async def override_get_current_user():
        return test_other_user_in_db

    test_app.dependency_overrides[get_current_user] = override_get_current_user

    # Create a new client for the other user
    other_client = await make_client(
        {"Authorization": f"Bearer {test_other_user_in_db.id}"}
    )

    # Add test_other_user as member (not admin/owner)
    workspace_service = WorkspaceService(db)
    workspace_service.add_member(
        workspace_id=test_workspace_in_db.id,
        user_id=test_other_user_in_db.id,
        role=WorkspaceRole.MEMBER,
    )

    response = await other_client.delete(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/{test_channel_in_db.slug}"
    )
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_channel_messages(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
):
    """Test listing messages in a channel."""
    response = await client.get(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/{test_channel_in_db.slug}/messages"
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_channel_messages_not_found(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
):
    """Test listing messages in a non-existent channel."""
    response = await client.get(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/non-existent/messages"
    )
    assert response.status_code == 404
    assert "channel not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_channel_message(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
):
    """Test creating a message in a channel."""
    response = await client.post(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/{test_channel_in_db.slug}/messages",
        json={
            "content": "Test message",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Test message"
    assert UUID(data["id"])
    assert data["channel_id"] == str(test_channel_in_db.id)


@pytest.mark.asyncio
async def test_create_channel_message_with_parent(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
):
    """Test creating a reply message in a channel."""
    # Create parent message first
    parent_response = await client.post(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/{test_channel_in_db.slug}/messages",
        json={
            "content": "Parent message",
        },
    )
    assert parent_response.status_code == 200
    parent_id = parent_response.json()["id"]

    # Create reply
    response = await client.post(
        f"/api/workspaces/{test_workspace_in_db.id}/channels/{test_channel_in_db.slug}/messages",
        json={
            "content": "Reply message",
            "parent_id": parent_id,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Reply message"
    assert data["parent_id"] == parent_id
