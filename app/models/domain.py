from typing import Optional, Any, TYPE_CHECKING, List
from pydantic import EmailStr
from uuid import UUID, uuid4

from sqlmodel import Column, DateTime, Field, Relationship, SQLModel, UniqueConstraint
from datetime import datetime, UTC
from app.models.types.file_type import FileType
from app.models.types.workspace_role import WorkspaceRole
from pgvector.sqlalchemy import Vector

if TYPE_CHECKING:
    from .domain import (
        Message,
        WorkspaceMember,
        File,
        UserEmbedding,
        DirectMessageConversation,
        AIConversation,
        Workspace,
        Reaction,
    )


class AIConversation(SQLModel, table=True):
    """AI conversation model."""

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="app_user.id", unique=True, index=True)

    # Note: We explicitly type the relationships for better type checking
    messages: List["Message"] = Relationship(
        back_populates="ai_conversation",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    files: Optional[List["File"]] = Relationship(
        back_populates="ai_conversation",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    user: "User" = Relationship(
        back_populates="ai_conversation",
        sa_relationship_kwargs={"foreign_keys": "[AIConversation.user_id]"},
    )

    # Add created_at and updated_at to all models
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # class Config:
    #     arbitrary_types_allowed = True


class Channel(SQLModel, table=True):
    """Channel model representing public/private channels in a workspace."""

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)

    name: str = Field(max_length=20, index=True)
    description: Optional[str] = Field(default=None, max_length=50)
    slug: str = Field(index=True, max_length=50)
    s3_key: Optional[str] = Field(default=None)
    created_by_id: UUID = Field(foreign_key="app_user.id")
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True)

    workspace: "Workspace" = Relationship(back_populates="channels")
    messages: Optional[List["Message"]] = Relationship(
        back_populates="channel",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    files: Optional[List["File"]] = Relationship(
        back_populates="channel",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    # Add created_at and updated_at to all models
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(
            DateTime(timezone=True),
            default=datetime.now(UTC),
            onupdate=datetime.now(UTC),
            nullable=False,
        ),
    )

    # class Config:
    #     arbitrary_types_allowed = True


class DirectMessageConversation(SQLModel, table=True):
    """Direct message conversation model."""

    __table_args__ = (
        UniqueConstraint("user1_id", "user2_id", name="unique_dm_conversation"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)

    user1_id: UUID = Field(foreign_key="app_user.id", index=True)
    user2_id: UUID = Field(foreign_key="app_user.id", index=True)

    messages: List["Message"] = Relationship(
        back_populates="dm_conversation",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    files: List["File"] = Relationship(
        back_populates="dm_conversation",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    user1: "User" = Relationship(
        back_populates="dm_conversations_as_user1",
        sa_relationship_kwargs={"foreign_keys": "[DirectMessageConversation.user1_id]"},
    )
    user2: "User" = Relationship(
        back_populates="dm_conversations_as_user2",
        sa_relationship_kwargs={"foreign_keys": "[DirectMessageConversation.user2_id]"},
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class FileEmbedding(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    file_id: UUID = Field(foreign_key="file.id", index=True)
    content: str = Field(index=True)
    embedding: Any = Field(sa_column=Column(Vector(dim=1536)))

    file: "File" = Relationship(back_populates="embeddings")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class File(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    name: str = Field(max_length=255)
    file_type: FileType = Field(default=FileType.OTHER)
    mime_type: str = Field(max_length=127)
    file_size: int
    message_id: UUID | None = Field(default=None, foreign_key="message.id", index=True)
    user_id: UUID = Field(foreign_key="app_user.id", index=True)
    workspace_id: UUID | None = Field(
        default=None, foreign_key="workspace.id", index=True
    )
    # Only one of these should be set
    channel_id: UUID | None = Field(default=None, foreign_key="channel.id", index=True)
    dm_conversation_id: UUID | None = Field(
        default=None, foreign_key="directmessageconversation.id", index=True
    )
    ai_conversation_id: UUID | None = Field(
        default=None, foreign_key="aiconversation.id", index=True
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    messages: Optional[List["Message"]] = Relationship(
        back_populates="file",
        sa_relationship_kwargs={
            "foreign_keys": "[Message.file_id]",
            "cascade": "all, delete-orphan",
        },
    )
    user: "User" = Relationship(back_populates="files")
    workspace: Optional["Workspace"] = Relationship(back_populates="files")
    channel: Optional["Channel"] = Relationship(back_populates="files")
    dm_conversation: Optional["DirectMessageConversation"] = Relationship(
        back_populates="files"
    )
    ai_conversation: Optional["AIConversation"] = Relationship(back_populates="files")
    embeddings: Optional[List["FileEmbedding"]] = Relationship(
        back_populates="file", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class MessageEmbedding(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    message_id: UUID = Field(foreign_key="message.id", index=True)
    content: str = Field(index=True)
    embedding: Any = Field(sa_column=Column(Vector(dim=1536)))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    message: "Message" = Relationship(back_populates="embeddings")


class Message(SQLModel, table=True):
    """Message model representing chat messages."""

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)

    content: str | None = Field(default=None)
    user_id: UUID | None = Field(default=None, foreign_key="app_user.id", index=True)
    is_ai_generated: bool = Field(default=False, index=True)

    # Only one of these should be set
    channel_id: Optional[UUID] = Field(
        default=None, foreign_key="channel.id", index=True
    )
    dm_conversation_id: Optional[UUID] = Field(
        default=None, foreign_key="directmessageconversation.id", index=True
    )
    ai_conversation_id: Optional[UUID] = Field(
        default=None, foreign_key="aiconversation.id", index=True
    )

    parent_id: Optional[UUID] = Field(
        default=None, foreign_key="message.id", index=True
    )
    file_id: Optional[UUID] = Field(default=None, foreign_key="file.id", index=True)
    file: Optional["File"] = Relationship(
        back_populates="messages",
        sa_relationship_kwargs={"foreign_keys": "[Message.file_id]", "cascade": "all"},
    )
    user: Optional["User"] = Relationship(
        back_populates="messages"
    )  # Optional for AI messages
    channel: Optional["Channel"] = Relationship(back_populates="messages")
    dm_conversation: Optional["DirectMessageConversation"] = Relationship(
        back_populates="messages"
    )
    ai_conversation: Optional["AIConversation"] = Relationship(
        back_populates="messages"
    )
    reactions: Optional[List["Reaction"]] = Relationship(
        back_populates="message",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    replies: Optional[List["Message"]] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    embeddings: Optional[List["MessageEmbedding"]] = Relationship(
        back_populates="message",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Reaction(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    emoji: str = Field(max_length=50)
    message_id: UUID = Field(foreign_key="message.id", index=True)
    user_id: UUID = Field(foreign_key="app_user.id", index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    message: "Message" = Relationship(back_populates="reactions")
    user: "User" = Relationship(back_populates="reactions")


class UserEmbedding(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="app_user.id", index=True)
    content: str = Field(index=True)
    embedding: Any = Field(sa_column=Column(Vector(dim=1536)))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    user: "User" = Relationship(back_populates="embeddings")


class WorkspaceMember(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="app_user.id", ondelete="CASCADE")
    workspace_id: UUID = Field(foreign_key="workspace.id", ondelete="CASCADE")
    role: WorkspaceRole = Field(default=WorkspaceRole.MEMBER, index=True)
    joined_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    workspace: "Workspace" = Relationship(
        back_populates="workspace_members",
        sa_relationship_kwargs={"overlaps": "members"},
    )
    user: "User" = Relationship(
        back_populates="workspace_members",
        sa_relationship_kwargs={"overlaps": "workspaces"},
    )


class User(SQLModel, table=True):
    """User model."""

    __tablename__: str = "app_user"  # Changed from "user" to avoid reserved keyword

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    email: EmailStr = Field(unique=True, index=True)
    username: str = Field(unique=True, index=True, max_length=20)
    hashed_password: str
    display_name: str = Field(max_length=20)
    s3_key: Optional[str] = Field(default=None)
    is_online: bool = Field(default=False, index=True)

    messages: Optional[List["Message"]] = Relationship(
        back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    workspace_members: Optional[List["WorkspaceMember"]] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
    )
    reactions: Optional[List["Reaction"]] = Relationship(
        back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    files: Optional[List["File"]] = Relationship(
        back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    workspaces: Optional[List["Workspace"]] = Relationship(
        back_populates="members",
        link_model=WorkspaceMember,
        sa_relationship_kwargs={
            "overlaps": "workspace_members",
            "viewonly": True,
        },
    )
    embeddings: Optional[List["UserEmbedding"]] = Relationship(
        back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    dm_conversations_as_user1: Optional[List["DirectMessageConversation"]] = (
        Relationship(
            back_populates="user1",
            sa_relationship_kwargs={
                "cascade": "all, delete-orphan",
                "foreign_keys": "[DirectMessageConversation.user1_id]",
            },
        )
    )
    dm_conversations_as_user2: Optional[List["DirectMessageConversation"]] = (
        Relationship(
            back_populates="user2",
            sa_relationship_kwargs={
                "cascade": "all, delete-orphan",
                "foreign_keys": "[DirectMessageConversation.user2_id]",
            },
        )
    )
    ai_conversation: Optional["AIConversation"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "foreign_keys": "[AIConversation.user_id]",
        },
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Workspace(SQLModel, table=True):
    """Workspace model representing a team/organization workspace."""

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)

    name: str = Field(max_length=20, index=True)
    description: str | None = Field(default=None, max_length=50)
    slug: str = Field(unique=True, index=True, max_length=100)
    s3_key: Optional[str] = Field(default=None)
    created_by_id: UUID = Field(foreign_key="app_user.id")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    workspace_members: Optional[List["WorkspaceMember"]] = Relationship(
        back_populates="workspace",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
    )
    members: Optional[List["User"]] = Relationship(
        back_populates="workspaces",
        link_model=WorkspaceMember,
        sa_relationship_kwargs={
            "overlaps": "workspace_members",
            "viewonly": True,
        },
    )
    channels: Optional[List["Channel"]] = Relationship(
        back_populates="workspace",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    files: Optional[List["File"]] = Relationship(
        back_populates="workspace",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
