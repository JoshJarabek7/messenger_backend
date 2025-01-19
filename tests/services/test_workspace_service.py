from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.domain import User, Workspace, WorkspaceMember
from app.models.types.workspace_role import WorkspaceRole
from app.services.user_service import UserService
from app.services.workspace_service import WorkspaceService

from sqlmodel import Session


@pytest.fixture
def workspace_service(db: Session):
    return WorkspaceService(db)


@pytest.fixture
def test_workspace_data():
    return {
        "name": "Test Workspace",
        "description": "A test workspace",
    }


@pytest.fixture
def test_other_user_in_db(db: Session) -> User:
    """Create another test user in the database."""
    user_service = UserService(db)
    return user_service.create_user(
        email="other@example.com",
        username="otheruser",
        password="testpassword123",
        display_name="Other User",
    )


@pytest.mark.asyncio
async def test_create_workspace_success(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_workspace_data: dict,
):
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    assert isinstance(workspace, Workspace)
    assert workspace.name == test_workspace_data["name"]
    assert workspace.description == test_workspace_data["description"]

    # Check that creator is added as owner
    members = workspace_service.get_members(workspace.id)
    assert len(members) == 1
    assert members[0].user_id == test_user_in_db.id
    assert members[0].role == WorkspaceRole.OWNER

    # Check that general channel is created
    channels = workspace_service.get_channels(workspace.id)
    assert len(channels) == 1
    assert channels[0].name == "general"


@pytest.mark.asyncio
async def test_get_workspace_success(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_workspace_data: dict,
):
    # Create workspace first
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    # Get workspace
    retrieved = workspace_service.get_workspace(workspace.id)
    assert retrieved.id == workspace.id
    assert retrieved.name == workspace.name


@pytest.mark.asyncio
async def test_get_workspace_not_found(
    workspace_service: WorkspaceService, test_user_in_db: User
):
    # Create and delete a workspace to get a valid but non-existent ID
    workspace = workspace_service.create_workspace(
        name="Test Workspace",
        description="Test workspace",
        created_by_id=test_user_in_db.id,
    )
    workspace_id = workspace.id
    workspace_service.delete_workspace(workspace_id, test_user_in_db.id)

    with pytest.raises(HTTPException) as exc_info:
        workspace_service.get_workspace(workspace_id)
    assert exc_info.value.status_code == 404
    assert "Workspace not found" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_by_slug_success(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_workspace_data: dict,
):
    # Create workspace first
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    # Get by slug
    retrieved = workspace_service.get_by_slug(workspace.slug)
    assert retrieved.id == workspace.id
    assert retrieved.name == workspace.name


@pytest.mark.asyncio
async def test_get_by_slug_not_found(workspace_service: WorkspaceService):
    with pytest.raises(HTTPException) as exc_info:
        workspace_service.get_by_slug("nonexistent-workspace")
    assert exc_info.value.status_code == 404
    assert "Workspace not found" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_user_workspaces(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_workspace_data: dict,
):
    # Create workspace first
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    # Get user workspaces
    workspaces = workspace_service.get_user_workspaces(test_user_in_db.id)
    assert len(workspaces) == 1
    assert workspaces[0].id == workspace.id


@pytest.mark.asyncio
async def test_update_workspace_success(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_workspace_data: dict,
):
    # Create workspace first
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    # Update workspace
    new_name = "Updated Workspace"
    new_description = "Updated description"
    updated = workspace_service.update_workspace(
        workspace.id,
        name=new_name,
        description=new_description,
        user_id=test_user_in_db.id,
    )

    assert updated.name == new_name
    assert updated.description == new_description


@pytest.mark.asyncio
async def test_update_workspace_unauthorized(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_other_user_in_db: User,
    test_workspace_data: dict,
):
    # Create workspace with one user
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    # Try to update with different user
    with pytest.raises(HTTPException) as exc_info:
        workspace_service.update_workspace(
            workspace_id=workspace.id,
            user_id=test_other_user_in_db.id,
            name="New name",
        )
    assert exc_info.value.status_code == 403
    assert "permission" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_delete_workspace_success(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_workspace_data: dict,
):
    # Create workspace first
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    # Delete workspace
    workspace_service.delete_workspace(workspace.id, test_user_in_db.id)

    # Verify workspace is deleted
    with pytest.raises(HTTPException) as exc_info:
        workspace_service.get_workspace(workspace.id)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_workspace_unauthorized(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_other_user_in_db: User,
    test_workspace_data: dict,
):
    # Create workspace with one user
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    # Try to delete with different user
    with pytest.raises(HTTPException) as exc_info:
        workspace_service.delete_workspace(workspace.id, test_other_user_in_db.id)
    assert exc_info.value.status_code == 403
    assert "permission" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_add_member_success(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_other_user_in_db: User,
    test_workspace_data: dict,
):
    # Create workspace first
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    # Add member
    member = workspace_service.add_member(
        workspace_id=workspace.id,
        user_id=test_other_user_in_db.id,
        role=WorkspaceRole.MEMBER,
    )

    assert isinstance(member, WorkspaceMember)
    assert member.workspace_id == workspace.id
    assert member.user_id == test_other_user_in_db.id
    assert member.role == WorkspaceRole.MEMBER


@pytest.mark.asyncio
async def test_remove_member_success(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_other_user_in_db: User,
    test_workspace_data: dict,
):
    # Create workspace first
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    # Add new member
    workspace_service.add_member(
        workspace_id=workspace.id,
        user_id=test_other_user_in_db.id,
        role=WorkspaceRole.MEMBER,
    )

    # Remove member
    workspace_service.remove_member(workspace.id, test_other_user_in_db.id)

    # Verify member is removed
    members = workspace_service.get_members(workspace.id)
    member_ids = {m.user_id for m in members}
    assert test_other_user_in_db.id not in member_ids


@pytest.mark.asyncio
async def test_update_member_role_success(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_other_user_in_db: User,
    test_workspace_data: dict,
):
    # Create workspace first
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    # Add new member
    member = workspace_service.add_member(
        workspace_id=workspace.id,
        user_id=test_other_user_in_db.id,
        role=WorkspaceRole.MEMBER,
    )

    # Update role
    updated = workspace_service.update_member_role(
        workspace_id=workspace.id,
        user_id=test_other_user_in_db.id,
        role=WorkspaceRole.ADMIN,
    )

    assert updated is not None
    assert updated.role == WorkspaceRole.ADMIN


@pytest.mark.asyncio
async def test_create_channel_success(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_workspace_data: dict,
):
    # Create workspace first
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    # Create channel
    channel = workspace_service.create_channel(
        workspace_id=workspace.id,
        name="test-channel",
        description="Test channel",
        created_by_id=test_user_in_db.id,
    )

    assert channel.name == "test-channel"
    assert channel.description == "Test channel"
    assert channel.workspace_id == workspace.id


@pytest.mark.asyncio
async def test_create_channel_unauthorized(
    workspace_service: WorkspaceService,
    test_user_in_db: User,
    test_other_user_in_db: User,
    test_workspace_data: dict,
):
    # Create workspace with one user
    workspace = workspace_service.create_workspace(
        name=test_workspace_data["name"],
        description=test_workspace_data["description"],
        created_by_id=test_user_in_db.id,
    )

    # Try to create channel with different user
    with pytest.raises(HTTPException) as exc_info:
        workspace_service.create_channel(
            workspace_id=workspace.id,
            name="test-channel",
            description="Test channel",
            created_by_id=test_other_user_in_db.id,
        )
    assert exc_info.value.status_code == 403
    assert "permission" in str(exc_info.value.detail).lower()
