from uuid import UUID

from fastapi import HTTPException

from loguru import logger
from sqlmodel import Session, select

from app.models.domain import Channel
from app.models.types.workspace_role import WorkspaceRole
from app.repositories.workspace_repository import WorkspaceRepository


class WorkspacePermissionService:
    """Service for managing workspace permissions"""

    def __init__(self, db: Session):
        self.db = db
        self.workspace_repository = WorkspaceRepository(db)

    def check_permission(
        self,
        user_id: UUID,
        workspace_id: UUID,
        required_role: WorkspaceRole | list[WorkspaceRole],
    ) -> bool:
        """Check if user has required role(s) in workspace"""
        role: WorkspaceRole | None = self.workspace_repository.get_member_role(
            workspace_id, user_id
        )
        if not role:
            return False

        # Owner has all permissions
        if role == WorkspaceRole.OWNER:
            return True

        # Admin has all permissions except owner
        if role == WorkspaceRole.ADMIN:
            if isinstance(required_role, list):
                return all(r != WorkspaceRole.OWNER for r in required_role)
            return required_role != WorkspaceRole.OWNER

        # Member only has member permissions
        if role == WorkspaceRole.MEMBER:
            if isinstance(required_role, list):
                return WorkspaceRole.MEMBER in required_role
            return required_role == WorkspaceRole.MEMBER

        return False

    def enforce_permission(
        self,
        user_id: UUID,
        workspace_id: UUID,
        required_role: WorkspaceRole | list[WorkspaceRole],
        error_message: str | None = None,
    ) -> None:
        """Enforce that user has required role(s) in workspace"""
        has_permission = self.check_permission(user_id, workspace_id, required_role)
        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail=error_message or "Insufficient workspace permissions",
            )

    def can_manage_channels(self, user_id: UUID, workspace_id: UUID) -> bool:
        """Check if user can manage channels in workspace"""
        role = self.workspace_repository.get_member_role(workspace_id, user_id)
        if not role:
            return False
        return role in [WorkspaceRole.OWNER, WorkspaceRole.ADMIN]

    def can_manage_members(self, user_id: UUID, workspace_id: UUID) -> bool:
        """Check if user can manage members in workspace"""
        role = self.workspace_repository.get_member_role(workspace_id, user_id)
        if not role:
            return False
        return role in [WorkspaceRole.OWNER, WorkspaceRole.ADMIN]

    def can_delete_workspace(self, user_id: UUID, workspace_id: UUID) -> bool:
        """Check if user can delete workspace"""
        role = self.workspace_repository.get_member_role(workspace_id, user_id)
        if not role:
            return False
        return role == WorkspaceRole.OWNER

    def can_update_workspace(self, user_id: UUID, workspace_id: UUID) -> bool:
        """Check if user can update workspace settings"""
        role = self.workspace_repository.get_member_role(workspace_id, user_id)
        if not role:
            return False
        return role in [WorkspaceRole.OWNER, WorkspaceRole.ADMIN]

    def can_invite_members(self, user_id: UUID, workspace_id: UUID) -> bool:
        """Check if user can invite new members"""
        role = self.workspace_repository.get_member_role(workspace_id, user_id)
        if not role:
            return False
        return role in [WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER]

    def can_remove_member(
        self, actor_id: UUID, workspace_id: UUID, target_id: UUID
    ) -> bool:
        """Check if actor can remove target member"""
        actor_role = self.workspace_repository.get_member_role(workspace_id, actor_id)
        target_role = self.workspace_repository.get_member_role(workspace_id, target_id)

        if not actor_role or not target_role:
            return False

        # Can't remove yourself if you're the owner
        if actor_id == target_id and target_role == WorkspaceRole.OWNER:
            return False

        # Owners can remove anyone
        if actor_role == WorkspaceRole.OWNER:
            return True

        # Admins can remove members and other admins
        if actor_role == WorkspaceRole.ADMIN:
            return target_role != WorkspaceRole.OWNER

        return False

    def can_update_member_role(
        self,
        actor_id: UUID,
        workspace_id: UUID,
        target_id: UUID,
        new_role: WorkspaceRole,
    ) -> bool:
        """Check if actor can update target member's role."""
        actor_role = self.workspace_repository.get_member_role(workspace_id, actor_id)
        target_role = self.workspace_repository.get_member_role(workspace_id, target_id)

        logger.info(
            f"Checking role update permission: actor={actor_id}, "
            f"workspace={workspace_id}, target={target_id}, new_role={new_role}"
        )
        logger.info(f"Current roles - Actor: {actor_role}, Target: {target_role}")

        # Basic validation
        if not actor_role or not target_role:
            logger.error(
                f"Role lookup failed - Actor: {actor_role}, Target: {target_role}"
            )
            return False

        # Check if actor has sufficient base permissions
        if actor_role not in [WorkspaceRole.OWNER, WorkspaceRole.ADMIN]:
            logger.info(
                f"Actor lacks sufficient permissions. Current role: {actor_role}"
            )
            return False

        # Cannot modify owners' roles
        if target_role == WorkspaceRole.OWNER:
            logger.info("Cannot modify owner's role")
            return False

        # Only owners can create new owners
        if new_role == WorkspaceRole.OWNER and actor_role != WorkspaceRole.OWNER:
            logger.info("Only owners can create new owners")
            return False

        # Admin-specific permissions
        if actor_role == WorkspaceRole.ADMIN:
            # Admins can only promote members to admin
            can_do = (
                target_role == WorkspaceRole.MEMBER and new_role == WorkspaceRole.ADMIN
            )
            logger.info(
                f"Admin attempting to modify role. Target role: {target_role}, "
                f"New role: {new_role}, Allowed: {can_do}"
            )
            return can_do

        # Owner permissions - owners can modify any non-owner role to any role
        # At this point, we know:
        # 1. Actor is an owner (only role left)
        # 2. Target is not an owner (checked above)
        # 3. New role permission has been validated
        logger.info(f"Owner modifying role from {target_role} to {new_role}")
        return True

    def can_view_channel(self, user_id: UUID, channel_id: UUID) -> bool:
        """Check if user can view channel"""
        channel = self.db.exec(
            select(Channel).where(Channel.id == channel_id)
        ).one_or_none()
        if not channel:
            return False

        role = self.workspace_repository.get_member_role(channel.workspace_id, user_id)
        if not role:
            return False
        return role in [WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER]
