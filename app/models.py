from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from uuid import UUID, uuid4
from datetime import datetime, UTC
from enum import Enum

def get_current_time():
    return datetime.now(UTC)

class ChannelType(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    DIRECT = "direct"

class WorkspaceMember(SQLModel, table=True):
    workspace_id: UUID = Field(foreign_key="workspace.id", primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", primary_key=True)
    role: str = Field(default="member")
    joined_at: datetime = Field(default_factory=get_current_time)

class ChannelMember(SQLModel, table=True):
    channel_id: UUID = Field(foreign_key="channel.id", primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", primary_key=True)
    joined_at: datetime = Field(default_factory=get_current_time)
    is_admin: bool = Field(default=False)

class Workspace(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    icon_url: Optional[str] = None
    created_at: datetime = Field(default_factory=get_current_time)
    created_by_id: UUID = Field(foreign_key="user.id")

    # Relationships
    channels: List["Channel"] = Relationship(back_populates="workspace")
    members: List["User"] = Relationship(back_populates="workspaces", link_model=WorkspaceMember)

class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    username: str = Field(unique=True, index=True)
    hashed_password: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    status: Optional[str] = None
    last_active: datetime = Field(default_factory=get_current_time)
    is_online: bool = Field(default=False)
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)

    # Relationships
    messages: List["Message"] = Relationship(back_populates="user")
    workspaces: List[Workspace] = Relationship(back_populates="members", link_model=WorkspaceMember)
    channels: List["Channel"] = Relationship(back_populates="members", link_model=ChannelMember)
    reactions: List["Reaction"] = Relationship(back_populates="user")
    sessions: List["UserSession"] = Relationship(back_populates="user")

class Channel(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    channel_type: ChannelType = Field(default=ChannelType.PUBLIC)
    workspace_id: UUID = Field(foreign_key="workspace.id")
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)

    participant_1_id: Optional[UUID] = Field(default=None, foreign_key="user.id")
    participant_2_id: Optional[UUID] = Field(default=None, foreign_key="user.id")

    # Relationships
    workspace: Workspace = Relationship(back_populates="channels")
    members: List["User"] = Relationship(back_populates="channels", link_model=ChannelMember)
    messages: List["Message"] = Relationship(back_populates="channel")

class Message(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    content: str
    user_id: UUID = Field(foreign_key="user.id")
    channel_id: UUID = Field(foreign_key="channel.id")
    parent_id: Optional[UUID] = Field(default=None, foreign_key="message.id")
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)

    # Relationships
    user: "User" = Relationship(back_populates="messages")
    channel: Channel = Relationship(back_populates="messages")
    reactions: List["Reaction"] = Relationship(back_populates="message")
    replies: List["Message"] = Relationship()  # For thread replies

class Reaction(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    emoji: str
    message_id: UUID = Field(foreign_key="message.id")
    user_id: UUID = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=get_current_time)

    # Relationships
    message: Message = Relationship(back_populates="reactions")
    user: "User" = Relationship(back_populates="reactions")

class FileAttachment(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    filename: str
    file_type: str
    file_size: int
    file_url: str
    message_id: UUID = Field(foreign_key="message.id")
    user_id: UUID = Field(foreign_key="user.id")
    uploaded_at: datetime = Field(default_factory=get_current_time)

class UserSession(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    session_id: str = Field(index=True)  # Store the WebSocket connection ID or session token
    connected_at: datetime = Field(default_factory=get_current_time)
    last_ping: datetime = Field(default_factory=get_current_time)

    # Relationship
    user: "User" = Relationship(back_populates="sessions")