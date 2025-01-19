from uuid import UUID, uuid4

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, and_, delete, select

from app.core.slug import create_slug
from app.models.domain import Channel, File, Workspace, WorkspaceMember
from app.models.types.workspace_role import WorkspaceRole
from app.repositories.base_repository import BaseRepository


class WorkspaceRepository(BaseRepository[Workspace]):
    """Repository for Workspace domain operations"""

    def __init__(self, db: Session):
        super().__init__(Workspace, db)

    def get_by_slug(self, slug: str) -> Workspace | None:
        statement = select(Workspace).where(Workspace.slug == slug)
        result = self.db.execute(statement)
        return result.scalar_one_or_none()

    def get_user_workspaces(self, user_id: UUID) -> list[Workspace]:
        """Get all workspaces a user is a member of"""
        try:
            statement = (
                select(Workspace)
                .join(WorkspaceMember)
                .where(WorkspaceMember.user_id == user_id)
            )
            result = self.db.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error getting user workspaces: {e}")
            raise e

    """ Member management within a workspace """

    def add_member(
        self, workspace_id: UUID, user_id: UUID, role: WorkspaceRole
    ) -> WorkspaceMember:
        """Add a user as a member of the workspace"""
        statement = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        existing_member = self.db.exec(statement).one_or_none()
        if existing_member:
            return existing_member

        member = WorkspaceMember(
            id=uuid4(), workspace_id=workspace_id, user_id=user_id, role=role
        )
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def remove_member(self, workspace_id: UUID, user_id: UUID) -> None:
        """Remove a user from the workspace"""
        statement = delete(WorkspaceMember).where(
            and_(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        self.db.execute(statement)
        self.db.commit()

    def get_members(self, workspace_id: UUID) -> list[WorkspaceMember]:
        statement = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id
        )
        result = self.db.execute(statement)
        return list(result.scalars().all())

    def update_member_role(
        self, workspace_id: UUID, user_id: UUID, role: WorkspaceRole
    ) -> WorkspaceMember | None:
        """Update a member's role in the workspace"""
        result = self.db.exec(
            select(WorkspaceMember).where(
                and_(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == user_id,
                )
            )
        )
        member = result.one_or_none()
        if member:
            member.role = role
            self.db.commit()
            self.db.refresh(member)
        return member

    def get_member_role(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceRole | None:
        statement = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        result = self.db.exec(statement)
        member: WorkspaceMember | None = result.one_or_none()
        return member.role if member else None

    # File operations
    def get_files(self, workspace_id: UUID) -> list[File]:
        statement = select(File).where(File.workspace_id == workspace_id)
        result = self.db.execute(statement)
        return list(result.scalars().all())

    # Channel management
    def create_channel(
        self,
        workspace_id: UUID,
        name: str,
        created_by_id: UUID,
        description: str | None = None,
    ) -> Channel:
        """Create a new channel in the workspace"""
        channel = Channel(
            id=uuid4(),
            name=name,
            description=description,
            workspace_id=workspace_id,
            slug=create_slug(name),
            created_by_id=created_by_id,
        )
        self.db.add(channel)
        self.db.commit()
        self.db.refresh(channel)

        return channel

    def get_channels(self, workspace_id: UUID) -> list[Channel]:
        """Get all channels in a workspace"""
        statement = select(Channel).where(Channel.workspace_id == workspace_id)
        result = self.db.execute(statement)
        return list(result.scalars().all())

    def get_channel(self, workspace_id: UUID, channel_slug: str) -> Channel | None:
        """Get a channel by its slug within a workspace"""
        statement = select(Channel).where(
            Channel.workspace_id == workspace_id,
            Channel.slug == channel_slug,
        )
        result = self.db.execute(statement)
        return result.scalar_one_or_none()

    def update_channel(self, channel: Channel) -> Channel:
        self.db.add(channel)
        self.db.commit()
        self.db.refresh(channel)
        return channel

    def add_file(self, file: File) -> File:
        self.db.add(file)
        self.db.commit()
        self.db.refresh(file)
        return file

    def delete_file(self, file_id: UUID) -> None:
        statement = delete(File).where(and_(File.id == file_id))
        self.db.execute(statement)
        self.db.commit()
