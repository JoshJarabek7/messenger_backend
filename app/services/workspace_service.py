from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session

from app.core.slug import create_slug
from app.models.domain import Channel, File, Workspace, WorkspaceMember
from app.models.types.workspace_role import WorkspaceRole
from app.repositories.channel_repository import ChannelRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.services.base_service import BaseService
from app.services.workspace_permission_service import WorkspacePermissionService
from app.services.user_service import UserService


class WorkspaceService(BaseService):
    """Service for managing workspace domain operations"""

    def __init__(self, db: Session):
        self.workspace_repository = WorkspaceRepository(db)
        self.channel_repository = ChannelRepository(db)
        self.permission_service = WorkspacePermissionService(db)
        self.user_service = UserService(db)
        self.db = db

    def create_workspace(
        self, name: str, description: str | None, created_by_id: UUID
    ) -> Workspace:
        """Create a new workspace and add the creator as owner"""
        # Create workspace
        workspace_data = {
            "name": name,
            "description": description,
            "created_by_id": created_by_id,
            "slug": create_slug(name),
        }
        workspace = self.workspace_repository.create(Workspace(**workspace_data))

        # Add creator as owner
        self.workspace_repository.add_member(
            workspace.id, created_by_id, WorkspaceRole.OWNER
        )

        # Commit the transaction to ensure owner permissions are set
        self.db.commit()

        # Create default general channel
        self.create_channel(
            workspace_id=workspace.id,
            name="general",
            created_by_id=created_by_id,
            description="General discussion channel",
        )

        return workspace

    def get_workspace(self, workspace_id: UUID) -> Workspace:
        """Get a workspace by ID"""
        workspace = self.workspace_repository.get(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    def get_by_slug(self, slug: str) -> Workspace:
        """Get a workspace by slug"""
        workspace = self.workspace_repository.get_by_slug(slug)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    def get_user_workspaces(self, user_id: UUID) -> list[Workspace]:
        """Get all workspaces a user is a member of"""
        return self.workspace_repository.get_user_workspaces(user_id)

    def update_workspace(
        self,
        workspace_id: UUID,
        user_id: UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> Workspace:
        """Update workspace details"""
        workspace = self.get_workspace(workspace_id)

        # Check if user can manage workspace
        if not self.permission_service.can_update_workspace(user_id, workspace_id):
            raise HTTPException(
                status_code=403,
                detail="User does not have permission to update workspace",
            )

        # Update fields if provided
        if name:
            workspace.name = name
            workspace.slug = create_slug(name)
        if description is not None:  # Allow empty description
            workspace.description = description

        return self.workspace_repository.update(workspace)

    def delete_workspace(self, workspace_id: UUID, user_id: UUID) -> None:
        """Delete a workspace and all its channels"""
        # Check if user can manage workspace
        if not self.permission_service.can_delete_workspace(user_id, workspace_id):
            raise HTTPException(
                status_code=403,
                detail="User does not have permission to delete workspace",
            )

        self.workspace_repository.delete(workspace_id)

    # Member management
    def add_member(
        self, workspace_id: UUID, user_id: UUID, role: WorkspaceRole
    ) -> WorkspaceMember:
        """Add a user as a member of the workspace"""
        return self.workspace_repository.add_member(workspace_id, user_id, role)

    def remove_member(self, workspace_id: UUID, user_id: UUID) -> None:
        """Remove a user from the workspace"""
        self.workspace_repository.remove_member(workspace_id, user_id)

    def get_members(self, workspace_id: UUID) -> list[WorkspaceMember]:
        """Get all members of a workspace"""
        return self.workspace_repository.get_members(workspace_id)

    def update_member_role(
        self, workspace_id: UUID, user_id: UUID, role: WorkspaceRole
    ) -> WorkspaceMember | None:
        """Update a member's role in the workspace"""
        return self.workspace_repository.update_member_role(workspace_id, user_id, role)

    # Channel management
    def create_channel(
        self,
        workspace_id: UUID,
        name: str,
        created_by_id: UUID,
        description: str | None = None,
    ) -> Channel:
        """Create a new channel in the workspace"""
        # Check if user can manage channels
        if not self.permission_service.can_manage_channels(created_by_id, workspace_id):
            raise HTTPException(
                status_code=403,
                detail="User does not have permission to create channels",
            )

        # Create channel with its conversation
        channel: Channel = self.workspace_repository.create_channel(
            workspace_id=workspace_id,
            name=name,
            description=description,
            created_by_id=created_by_id,
        )

        return channel

    def delete_channel(
        self,
        workspace_id: UUID,
        channel_id: UUID,
        user_id: UUID,
    ) -> None:
        """Delete a channel from the workspace"""
        # Check if user can manage channels
        if not self.permission_service.can_manage_channels(user_id, workspace_id):
            raise HTTPException(
                status_code=403,
                detail="User does not have permission to delete channels",
            )

        # Verify channel belongs to workspace
        channel = self.channel_repository.get(channel_id)
        if not channel or channel.workspace_id != workspace_id:
            raise HTTPException(
                status_code=404, detail="Channel not found in workspace"
            )

        self.channel_repository.delete(channel_id)

    def update_channel(
        self,
        channel_id: UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> Channel:
        """Update a channel"""
        channel = self.channel_repository.get(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        if name:
            channel.name = name
        if description:
            channel.description = description
        return self.channel_repository.update(channel)

    def get_channels(self, workspace_id: UUID) -> list[Channel]:
        """Get all channels in a workspace"""
        return self.workspace_repository.get_channels(workspace_id)

    def get_channel(self, workspace_id: UUID, channel_slug: str) -> Channel | None:
        """Get a channel by its slug within a workspace"""
        return self.workspace_repository.get_channel(workspace_id, channel_slug)

    # File operations
    async def get_files(self, workspace_id: UUID) -> list[File]:
        """Get all files in a workspace"""
        return self.workspace_repository.get_files(workspace_id)
