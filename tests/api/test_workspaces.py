from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import Session

from app.models.domain import User, Workspace, WorkspaceMember
from app.models.types.workspace_role import WorkspaceRole
from app.services.workspace_service import WorkspaceService


@pytest.fixture
def test_workspace_in_db(db: Session, test_user_in_db: User) -> Workspace:
    """Create a test workspace in the database."""
    workspace_service = WorkspaceService(db)
    return workspace_service.create_workspace(
        name="Test Workspace",
        description="Test workspace description",
        created_by_id=test_user_in_db.id,
    )


@pytest.mark.asyncio
async def test_list_workspaces(client: AsyncClient, test_workspace_in_db: Workspace):
    """Test listing workspaces."""
    response = await client.get("/api/workspaces/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(workspace["id"] == str(test_workspace_in_db.id) for workspace in data)


@pytest.mark.asyncio
async def test_create_workspace(client: AsyncClient):
    """Test creating a new workspace."""
    response = await client.post(
        "/api/workspaces/",
        json={
            "name": "New Workspace",
            "description": "A new test workspace",
        },
    )
    assert response.status_code == 200
    data = response.json()
    print(f"Response data: {data}")  # Debug print
    assert data["name"] == "New Workspace"
    assert data["description"] == "A new test workspace"
    assert UUID(data["id"])
    assert "slug" in data  # Verify slug is present
    assert "created_by_id" in data  # Verify creator is set


@pytest.mark.asyncio
async def test_get_workspace(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
):
    """Test getting a specific workspace."""
    response = await client.get(f"/api/workspaces/{test_workspace_in_db.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_workspace_in_db.id)
    assert data["name"] == test_workspace_in_db.name
    assert data["description"] == test_workspace_in_db.description


@pytest.mark.asyncio
async def test_update_workspace(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
):
    """Test updating a workspace."""
    response = await client.put(
        f"/api/workspaces/{test_workspace_in_db.id}",
        json={
            "name": "Updated Workspace",
            "description": "Updated description",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Workspace"
    assert data["description"] == "Updated description"


@pytest.mark.asyncio
async def test_delete_workspace(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
):
    """Test deleting a workspace."""
    response = await client.delete(f"/api/workspaces/{test_workspace_in_db.id}")
    assert response.status_code == 200
    assert response.json()["message"] == "Workspace deleted successfully"

    # Verify workspace is deleted
    response = await client.get(f"/api/workspaces/{test_workspace_in_db.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_workspace_members(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
    test_user_in_db: User,
):
    """Test listing workspace members."""
    response = await client.get(f"/api/workspaces/{test_workspace_in_db.id}/members")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1  # Should have at least the creator
    assert any(
        member["user_id"] == str(test_user_in_db.id)
        and member["role"] == WorkspaceRole.OWNER.value
        for member in data
    )


@pytest.mark.asyncio
async def test_add_workspace_member(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
    test_other_user_in_db: User,
):
    """Test adding a member to a workspace."""
    response = await client.post(
        f"/api/workspaces/{test_workspace_in_db.id}/members",
        json={
            "user_id": str(test_other_user_in_db.id),
            "role": WorkspaceRole.MEMBER.value,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(test_other_user_in_db.id)
    assert data["role"] == WorkspaceRole.MEMBER.value


@pytest.mark.asyncio
async def test_remove_workspace_member(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
    test_other_user_in_db: User,
    db: Session,
):
    """Test removing a member from a workspace."""
    # Add member first
    workspace_service = WorkspaceService(db)
    workspace_service.add_member(
        workspace_id=test_workspace_in_db.id,
        user_id=test_other_user_in_db.id,
        role=WorkspaceRole.MEMBER,
    )

    response = await client.delete(
        f"/api/workspaces/{test_workspace_in_db.id}/members/{test_other_user_in_db.id}"
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Member removed successfully"

    # Verify member is removed
    members = workspace_service.get_members(test_workspace_in_db.id)
    assert not any(member.user_id == test_other_user_in_db.id for member in members)


@pytest.mark.asyncio
async def test_update_member_role(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
    test_other_user_in_db: User,
    db: Session,
):
    """Test updating a member's role."""
    # Add member first
    workspace_service = WorkspaceService(db)
    workspace_service.add_member(
        workspace_id=test_workspace_in_db.id,
        user_id=test_other_user_in_db.id,
        role=WorkspaceRole.MEMBER,
    )

    response = await client.put(
        f"/api/workspaces/{test_workspace_in_db.id}/members/{test_other_user_in_db.id}/role",
        json={
            "role": WorkspaceRole.ADMIN.value,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(test_other_user_in_db.id)
    assert data["role"] == WorkspaceRole.ADMIN.value


@pytest.mark.asyncio
async def test_update_member_role_not_found(
    client: AsyncClient,
    test_workspace_in_db: Workspace,
):
    """Test updating role of a non-existent member."""
    response = await client.put(
        f"/api/workspaces/{test_workspace_in_db.id}/members/{UUID(int=0)}/role",
        json={
            "role": WorkspaceRole.ADMIN.value,
        },
    )
    assert response.status_code == 404
    assert "member not found" in response.json()["detail"].lower()
