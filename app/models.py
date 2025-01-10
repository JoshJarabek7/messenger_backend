from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

from app.utils.time import get_current_time


class ChannelType(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    DIRECT = "DIRECT"


class FileType(str, Enum):
    IMAGE = "image"
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    PDF = "pdf"
    VIDEO = "video"
    AUDIO = "audio"
    OTHER = "other"

    @classmethod
    def from_mime_type(cls, mime_type: str) -> "FileType":
        """Determine FileType from MIME type"""
        mime_map = {
            "image/": cls.IMAGE,
            "video/": cls.VIDEO,
            "audio/": cls.AUDIO,
            "application/pdf": cls.PDF,
            "application/vnd.ms-excel": cls.SPREADSHEET,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": cls.SPREADSHEET,
            "application/msword": cls.DOCUMENT,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": cls.DOCUMENT,
            "application/vnd.ms-powerpoint": cls.PRESENTATION,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": cls.PRESENTATION,
        }

        for mime_prefix, file_type in mime_map.items():
            if mime_type.startswith(mime_prefix):
                return file_type
        return cls.OTHER

    @classmethod
    def from_filename(cls, filename: str) -> "FileType":
        """Determine FileType from file extension"""
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        ext_map = {
            "pdf": cls.PDF,
            "doc": cls.DOCUMENT,
            "docx": cls.DOCUMENT,
            "xls": cls.SPREADSHEET,
            "xlsx": cls.SPREADSHEET,
            "ppt": cls.PRESENTATION,
            "pptx": cls.PRESENTATION,
            "jpg": cls.IMAGE,
            "jpeg": cls.IMAGE,
            "png": cls.IMAGE,
            "gif": cls.IMAGE,
            "webp": cls.IMAGE,
            "mp4": cls.VIDEO,
            "mov": cls.VIDEO,
            "avi": cls.VIDEO,
            "mp3": cls.AUDIO,
            "wav": cls.AUDIO,
            "ogg": cls.AUDIO,
        }
        return ext_map.get(ext, cls.OTHER)


class WorkspaceMember(SQLModel, table=True):
    workspace_id: UUID = Field(foreign_key="workspace.id", primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", primary_key=True)
    role: str = Field(default="member")
    joined_at: datetime = Field(default_factory=get_current_time)


class ConversationMember(SQLModel, table=True):
    conversation_id: UUID = Field(foreign_key="conversation.id", primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", primary_key=True)
    joined_at: datetime = Field(default_factory=get_current_time)
    is_admin: bool = Field(default=False)


class Workspace(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    slug: str = Field(unique=True, index=True)
    icon_url: Optional[str] = None
    created_at: datetime = Field(default_factory=get_current_time)
    created_by_id: UUID = Field(foreign_key="user.id")

    # Relationships
    conversations: List["Conversation"] = Relationship(back_populates="workspace")
    members: List["User"] = Relationship(
        back_populates="workspaces", link_model=WorkspaceMember
    )


class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    username: str = Field(unique=True, index=True)
    hashed_password: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    status: Optional[str] = None
    last_active: datetime = Field(default_factory=get_current_time)
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)

    # Relationships
    messages: List["Message"] = Relationship(back_populates="user")
    workspaces: List[Workspace] = Relationship(
        back_populates="members", link_model=WorkspaceMember
    )
    conversations: List["Conversation"] = Relationship(
        back_populates="members", link_model=ConversationMember
    )
    reactions: List["Reaction"] = Relationship(back_populates="user")
    sessions: List["UserSession"] = Relationship(back_populates="user")


class Message(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    content: Optional[str] = (
        None  # Making content optional since a message might just have attachments
    )
    user_id: UUID = Field(foreign_key="user.id")
    conversation_id: Optional[UUID] = Field(default=None, foreign_key="conversation.id")
    parent_id: Optional[UUID] = Field(default=None, foreign_key="message.id")
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)

    # Relationships
    attachments: List["FileAttachment"] = Relationship(back_populates="message")
    user: "User" = Relationship(back_populates="messages")
    conversation: Optional["Conversation"] = Relationship(back_populates="messages")
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
    original_filename: str  # Original filename from user
    s3_key: str  # UUID-based key in S3
    file_type: FileType = Field(default=FileType.OTHER)
    mime_type: str  # Store the actual MIME type for precise handling
    file_size: int
    uploaded_at: datetime = Field(default_factory=get_current_time)
    upload_completed: bool = Field(
        default=False
    )  # Track if the file was successfully uploaded
    message_id: Optional[UUID] = Field(
        default=None, foreign_key="message.id"
    )  # Make message_id optional
    user_id: UUID = Field(foreign_key="user.id")

    # Relationships
    message: Optional[Message] = Relationship(back_populates="attachments")


class UserSession(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    session_id: str = Field(
        index=True
    )  # Store the WebSocket connection ID or session token
    connected_at: datetime = Field(default_factory=get_current_time)
    last_ping: datetime = Field(default_factory=get_current_time)

    # Relationship
    user: "User" = Relationship(back_populates="sessions")


class Conversation(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str | None = None
    description: str | None = None
    conversation_type: ChannelType = Field(
        default=ChannelType.DIRECT
    )  # Reusing ChannelType enum
    participant_1_id: Optional[UUID] = Field(default=None, foreign_key="user.id")
    participant_2_id: Optional[UUID] = Field(default=None, foreign_key="user.id")
    workspace_id: Optional[UUID] = Field(default=None, foreign_key="workspace.id")
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)

    # Relationships
    messages: List[Message] = Relationship(back_populates="conversation")
    workspace: Optional[Workspace] = Relationship(back_populates="conversations")
    members: List["User"] = Relationship(
        back_populates="conversations", link_model=ConversationMember
    )
