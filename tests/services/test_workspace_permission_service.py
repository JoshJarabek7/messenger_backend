from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from app.models.domain import User, Workspace, WorkspaceMember, Channel
from app.models.types.workspace_role import WorkspaceRole
from app.services.user_service import UserService
from app.services.workspace_service import WorkspaceService
from app.services.workspace_permission_service import WorkspacePermissionService


@pytest.fixture
def permission_service(db: Session):
    return WorkspacePermissionService(db)


@pytest.fixture
def test_workspace_in_db(db: Session, test_user_in_db: User) -> Workspace:
    """Create a test workspace in the database."""
    workspace_service = WorkspaceService(db)
    workspace = workspace_service.create_workspace(
        name="Test Workspace",
        description="Test workspace description",
        created_by_id=test_user_in_db.id,
    )
    db.commit()  # Ensure all changes are committed
    return workspace


@pytest.fixture
def workspace_service(db: Session) -> WorkspaceService:
    """Create a WorkspaceService instance."""
    return WorkspaceService(db)


@pytest.fixture
def test_channel_in_db(
    db: Session, test_workspace_in_db: Workspace, test_user_in_db: User
) -> Channel:
    """Create a test channel in the database."""
    workspace_service = WorkspaceService(db)
    channel = workspace_service.create_channel(
        workspace_id=test_workspace_in_db.id,
        name="test-channel",
        description="Test channel",
        created_by_id=test_user_in_db.id,
    )
    db.commit()  # Ensure all changes are committed
    return channel


@pytest.mark.asyncio
async def test_check_permission_owner(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_user_in_db: User,
):
    """Test that owner has all permissions."""
    # Owner should have owner role
    assert permission_service.check_permission(
        test_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.OWNER,
    )

    # Owner should also have admin permissions
    assert permission_service.check_permission(
        test_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.ADMIN,
    )

    # Owner should also have member permissions
    assert permission_service.check_permission(
        test_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.MEMBER,
    )


@pytest.mark.asyncio
async def test_check_permission_admin(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_user_in_db: User,
    test_other_user_in_db: User,
    workspace_service: WorkspaceService,
    db: Session,
):
    """Test that admin has appropriate permissions."""
    # Add other user as admin
    workspace_service.add_member(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.ADMIN,
    )
    db.commit()  # Commit the transaction

    # Admin should not have owner permissions
    assert not permission_service.check_permission(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.OWNER,
    )

    # Admin should have admin permissions
    assert permission_service.check_permission(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.ADMIN,
    )

    # Admin should have member permissions
    assert permission_service.check_permission(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.MEMBER,
    )


@pytest.mark.asyncio
async def test_check_permission_member(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_user_in_db: User,
    test_other_user_in_db: User,
    workspace_service: WorkspaceService,
    db: Session,
):
    """Test that member has appropriate permissions."""
    # Add other user as member
    workspace_service.add_member(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.MEMBER,
    )
    db.commit()  # Commit the transaction

    # Member should not have owner permissions
    assert not permission_service.check_permission(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.OWNER,
    )

    # Member should not have admin permissions
    assert not permission_service.check_permission(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.ADMIN,
    )

    # Member should have member permissions
    assert permission_service.check_permission(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.MEMBER,
    )


@pytest.mark.asyncio
async def test_check_permission_non_member(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_other_user_in_db: User,
):
    """Test that non-member has no permissions."""
    # Non-member should not have any permissions
    assert not permission_service.check_permission(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.OWNER,
    )
    assert not permission_service.check_permission(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.ADMIN,
    )
    assert not permission_service.check_permission(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.MEMBER,
    )


@pytest.mark.asyncio
async def test_enforce_permission_success(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_user_in_db: User,
):
    """Test that enforce_permission succeeds for valid permissions."""
    # Should not raise exception for owner
    permission_service.enforce_permission(
        test_user_in_db.id,
        test_workspace_in_db.id,
        WorkspaceRole.OWNER,
    )


@pytest.mark.asyncio
async def test_enforce_permission_failure(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_other_user_in_db: User,
):
    """Test that enforce_permission raises exception for invalid permissions."""
    with pytest.raises(HTTPException) as exc_info:
        permission_service.enforce_permission(
            test_other_user_in_db.id,
            test_workspace_in_db.id,
            WorkspaceRole.OWNER,
        )
    assert exc_info.value.status_code == 403
    assert "Insufficient workspace permissions" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_can_manage_channels(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_user_in_db: User,
    test_other_user_in_db: User,
    workspace_service: WorkspaceService,
    db: Session,
):
    """Test channel management permissions."""
    # Owner can manage channels
    assert permission_service.can_manage_channels(
        test_user_in_db.id,
        test_workspace_in_db.id,
    )

    # Add admin user
    workspace_service.add_member(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.ADMIN,
    )
    db.commit()  # Commit the transaction

    # Admin can manage channels
    assert permission_service.can_manage_channels(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
    )

    # Change to member
    workspace_service.update_member_role(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.MEMBER,
    )
    db.commit()  # Commit the transaction

    # Member cannot manage channels
    assert not permission_service.can_manage_channels(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
    )


@pytest.mark.asyncio
async def test_can_manage_members(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_user_in_db: User,
    test_other_user_in_db: User,
    workspace_service: WorkspaceService,
    db: Session,
):
    """Test member management permissions."""
    # Owner can manage members
    assert permission_service.can_manage_members(
        test_user_in_db.id,
        test_workspace_in_db.id,
    )

    # Add admin user
    workspace_service.add_member(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.ADMIN,
    )
    db.commit()  # Commit the transaction

    # Admin can manage members
    assert permission_service.can_manage_members(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
    )

    # Change to member
    workspace_service.update_member_role(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.MEMBER,
    )
    db.commit()  # Commit the transaction

    # Member cannot manage members
    assert not permission_service.can_manage_members(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
    )


@pytest.mark.asyncio
async def test_can_delete_workspace(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_user_in_db: User,
    test_other_user_in_db: User,
    workspace_service: WorkspaceService,
    db: Session,
):
    """Test workspace deletion permissions."""
    # Owner can delete workspace
    assert permission_service.can_delete_workspace(
        test_user_in_db.id,
        test_workspace_in_db.id,
    )

    # Add admin user
    workspace_service.add_member(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.ADMIN,
    )
    db.commit()  # Commit the transaction

    # Admin cannot delete workspace
    assert not permission_service.can_delete_workspace(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
    )


@pytest.mark.asyncio
async def test_can_update_workspace(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_user_in_db: User,
    test_other_user_in_db: User,
    workspace_service: WorkspaceService,
    db: Session,
):
    """Test workspace update permissions."""
    # Owner can update workspace
    assert permission_service.can_update_workspace(
        test_user_in_db.id,
        test_workspace_in_db.id,
    )

    # Add admin user
    workspace_service.add_member(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.ADMIN,
    )
    db.commit()  # Commit the transaction

    # Admin can update workspace
    assert permission_service.can_update_workspace(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
    )

    # Change to member
    workspace_service.update_member_role(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.MEMBER,
    )
    db.commit()  # Commit the transaction

    # Member cannot update workspace
    assert not permission_service.can_update_workspace(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
    )


@pytest.mark.asyncio
async def test_can_invite_members(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_user_in_db: User,
    test_other_user_in_db: User,
    workspace_service: WorkspaceService,
    db: Session,
):
    """Test member invitation permissions."""
    # Owner can invite members
    assert permission_service.can_invite_members(
        test_user_in_db.id,
        test_workspace_in_db.id,
    )

    # Add member user
    workspace_service.add_member(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.MEMBER,
    )
    db.commit()  # Commit the transaction

    # Member can invite members
    assert permission_service.can_invite_members(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
    )


@pytest.mark.asyncio
async def test_can_remove_member(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_user_in_db: User,
    test_other_user_in_db: User,
    workspace_service: WorkspaceService,
    db: Session,
):
    """Test member removal permissions."""
    # Add member to be removed
    workspace_service.add_member(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.MEMBER,
    )
    db.commit()  # Commit the transaction

    # Owner can remove member
    assert permission_service.can_remove_member(
        test_user_in_db.id,
        test_workspace_in_db.id,
        test_other_user_in_db.id,
    )

    # Member cannot remove other member
    assert not permission_service.can_remove_member(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
        test_user_in_db.id,
    )

    # Change to admin
    workspace_service.update_member_role(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.ADMIN,
    )
    db.commit()  # Commit the transaction

    # Admin can remove members but not owner
    assert not permission_service.can_remove_member(
        test_other_user_in_db.id,
        test_workspace_in_db.id,
        test_user_in_db.id,  # owner
    )


@pytest.mark.asyncio
async def test_can_update_member_role(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_user_in_db: User,
    test_other_user_in_db: User,
    workspace_service: WorkspaceService,
    db: Session,
):
    """Test member role update permissions with proper role hierarchy enforcement.

    This test validates that:
    1. Owners can promote members to admin or owner
    2. Admins can only promote members to admin
    3. Admins cannot modify owner roles
    4. Members cannot modify any roles
    """
    # First, add a regular member to the workspace
    workspace_service.add_member(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.MEMBER,
    )
    db.commit()

    # Test Case 1: Owner promotes member to admin
    # This should be allowed - owners can promote members to any role
    assert permission_service.can_update_member_role(
        test_user_in_db.id,  # Owner
        test_workspace_in_db.id,
        test_other_user_in_db.id,  # Member
        WorkspaceRole.ADMIN,
    )

    # Actually promote the member to admin
    workspace_service.update_member_role(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.ADMIN,
    )
    db.commit()

    # Test Case 2: Admin tries to modify owner's role
    # This should be denied - admins cannot modify owner roles
    assert not permission_service.can_update_member_role(
        test_other_user_in_db.id,  # Admin
        test_workspace_in_db.id,
        test_user_in_db.id,  # Owner
        WorkspaceRole.MEMBER,  # Trying to demote owner
    )

    # Test Case 3: Add another member to test admin permissions
    new_member = UserService(db).create_user(
        email="newmember@test.com",
        username="newmember",
        password="testpass123",
        display_name="New Member",
    )
    workspace_service.add_member(
        test_workspace_in_db.id,
        new_member.id,
        WorkspaceRole.MEMBER,
    )
    db.commit()

    # Test Case 4: Admin promotes regular member to admin
    # This should be allowed - admins can promote members to admin
    assert permission_service.can_update_member_role(
        test_other_user_in_db.id,  # Admin
        test_workspace_in_db.id,
        new_member.id,  # Member
        WorkspaceRole.ADMIN,
    )

    # Test Case 5: Admin tries to promote member to owner
    # This should be denied - only owners can create new owners
    assert not permission_service.can_update_member_role(
        test_other_user_in_db.id,  # Admin
        test_workspace_in_db.id,
        new_member.id,  # Member
        WorkspaceRole.OWNER,
    )

    # Test Case 6: Owner can still promote members to any role
    assert permission_service.can_update_member_role(
        test_user_in_db.id,  # Owner
        test_workspace_in_db.id,
        new_member.id,  # Member
        WorkspaceRole.OWNER,
    )


@pytest.mark.asyncio
async def test_can_view_channel(
    permission_service: WorkspacePermissionService,
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
    test_user_in_db: User,
    test_other_user_in_db: User,
    workspace_service: WorkspaceService,
    db: Session,
):
    """Test channel viewing permissions."""
    # Owner can view channel
    assert permission_service.can_view_channel(
        test_user_in_db.id,
        test_channel_in_db.id,
    )

    # Add member
    workspace_service.add_member(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
        WorkspaceRole.MEMBER,
    )
    db.commit()  # Commit the transaction

    # Member can view channel
    assert permission_service.can_view_channel(
        test_other_user_in_db.id,
        test_channel_in_db.id,
    )

    # Non-member cannot view channel
    workspace_service.remove_member(
        test_workspace_in_db.id,
        test_other_user_in_db.id,
    )
    db.commit()  # Commit the transaction
    assert not permission_service.can_view_channel(
        test_other_user_in_db.id,
        test_channel_in_db.id,
    )
