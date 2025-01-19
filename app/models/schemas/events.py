from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, model_validator
from enum import Enum
from typing_extensions import Self

from app.models.schemas.responses.user import UserResponse
from app.models.schemas.responses.workspace import WorkspaceResponse
from app.models.types.workspace_role import WorkspaceRole


class EventType(str, Enum):
    """Enum for all possible event types in the system"""

    # Error events
    ERROR = "error"

    # Message events
    MESSAGE_CREATED = "message_created"
    MESSAGE_DELETED = "message_deleted"

    # Reaction events
    REACTION_ADDED = "reaction_added"
    REACTION_REMOVED = "reaction_removed"

    # Conversation events
    TYPING_STARTED = "typing_started"
    TYPING_STOPPED = "typing_stopped"

    # User events
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_ONLINE = "user_online"
    USER_OFFLINE = "user_offline"

    # AI events
    AI_MESSAGE_STARTED = "ai_message_started"
    AI_MESSAGE_CHUNK = "ai_message_chunk"
    AI_MESSAGE_COMPLETED = "ai_message_completed"
    AI_ERROR = "ai_error"

    # File events
    FILE_CREATED = "file_created"
    FILE_DELETED = "file_deleted"

    # Workspace events
    WORKSPACE_CREATED = "workspace_created"
    WORKSPACE_UPDATED = "workspace_updated"
    WORKSPACE_DELETED = "workspace_deleted"
    WORKSPACE_MEMBER_ADDED = "workspace_member_added"
    WORKSPACE_MEMBER_REMOVED = "workspace_member_removed"
    WORKSPACE_MEMBER_UPDATED = "workspace_member_updated"


class BaseEvent(BaseModel):
    """Base schema for all events"""

    type: EventType
    data: BaseModel


""" Typing Status Event """


class TypingStatusData(BaseModel):
    """Schema for typing status updates"""

    dm_conversation_id: UUID | None = None
    channel_id: UUID | None = None
    ai_conversation_id: UUID | None = None
    id: UUID
    is_typing: bool

    @model_validator(mode="after")
    def validate_conversation_id(self) -> Self:
        if (
            not self.dm_conversation_id
            and not self.channel_id
            and not self.ai_conversation_id
        ):
            raise ValueError("At least one conversation id must be provided")
        return self


class TypingEvent(BaseEvent):
    type: Literal[EventType.TYPING_STARTED, EventType.TYPING_STOPPED]
    data: TypingStatusData


""" Chat Message Creation Event """


class ChatMessageData(BaseModel):
    id: UUID
    content: str = ""
    user_id: UUID
    is_ai_generated: bool = False
    channel_id: UUID | None = None
    dm_conversation_id: UUID | None = None
    ai_conversation_id: UUID | None = None
    parent_id: UUID | None = None
    file_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_conversation_id(self) -> Self:
        if not (self.dm_conversation_id or self.channel_id or self.ai_conversation_id):
            raise ValueError("At least one conversation id must be provided")
        return self

    @model_validator(mode="after")
    def validate_ai_generated(self) -> Self:
        if self.is_ai_generated and not self.ai_conversation_id:
            raise ValueError("AI conversations must have an ai_conversation_id")
        return self

    @model_validator(mode="after")
    def validate_non_parent_for_ai(self) -> Self:
        if self.ai_conversation_id and self.parent_id:
            raise ValueError("AI conversations don't support threads")
        return self


class ChatMessageCreatedEvent(BaseEvent):
    type: Literal[EventType.MESSAGE_CREATED]
    data: ChatMessageData


""" Chat Message Deletion Event """


class ChatMessageDeletedEvent(BaseEvent):
    type: Literal[EventType.MESSAGE_DELETED]
    data: ChatMessageData


""" Reaction Events """


class ReactionAddedData(BaseModel):
    id: UUID
    emoji: str
    user_id: UUID
    message_id: UUID
    created_at: datetime
    updated_at: datetime


class ReactionAddedEvent(BaseEvent):
    type: Literal[EventType.REACTION_ADDED]
    data: ReactionAddedData


class ReactionRemovedData(BaseModel):
    message_id: UUID
    user_id: UUID
    id: UUID


class ReactionRemovedEvent(BaseEvent):
    type: Literal[EventType.REACTION_REMOVED]
    data: ReactionRemovedData


""" User Events """


class UserUpdatedEvent(BaseEvent):
    type: Literal[EventType.USER_UPDATED]
    data: UserResponse


class UserDeletedData(BaseModel):
    id: UUID


class UserDeletedEvent(BaseEvent):
    type: Literal[EventType.USER_DELETED]
    data: UserDeletedData


class UserPresenceData(BaseModel):
    id: UUID
    is_online: bool


class UserOnlineEvent(BaseEvent):
    type: Literal[EventType.USER_ONLINE]
    data: UserPresenceData

    @model_validator(mode="after")
    def validate_online(self) -> Self:
        if not self.data.is_online:
            raise ValueError("User must be online")
        return self


class UserOfflineEvent(BaseEvent):
    type: Literal[EventType.USER_OFFLINE]
    data: UserPresenceData

    @model_validator(mode="after")
    def validate_offline(self) -> Self:
        if self.data.is_online:
            raise ValueError("User must be offline")
        return self


""" AI EVENTS """


class AIMessageStreamStage(str, Enum):
    STARTED = "started"
    CHUNK = "chunk"
    COMPLETED = "completed"
    ERROR = "error"


class AIMessageData(BaseModel):
    id: UUID
    user_id: UUID
    ai_conversation_id: UUID
    content: str | None = None
    stream_stage: AIMessageStreamStage
    error: str | None = None

    @model_validator(mode="after")
    def stream_stage_started(self) -> Self:
        if self.stream_stage == AIMessageStreamStage.STARTED:
            if self.content:
                raise ValueError("Content must be None when stream stage is started")
            if self.error:
                raise ValueError("Error must be None when stream stage is started")
        return self

    @model_validator(mode="after")
    def stream_stage_chunk(self) -> Self:
        if self.stream_stage == AIMessageStreamStage.CHUNK:
            if not self.content:
                raise ValueError("Content must be provided when stream stage is chunk")
            if self.error:
                raise ValueError("Error must be None when stream stage is chunk")
        return self

    @model_validator(mode="after")
    def stream_stage_completed(self) -> Self:
        if self.stream_stage == AIMessageStreamStage.COMPLETED:
            if self.content:
                raise ValueError("Completed messages must not have content")
            if self.error:
                raise ValueError("Completed messages must not have error")
        return self

    @model_validator(mode="after")
    def stream_stage_error(self) -> Self:
        if self.stream_stage == AIMessageStreamStage.ERROR:
            if not self.error:
                raise ValueError("Error must be provided when stream stage is error")
            if self.content:
                raise ValueError("Error messages must not have content")
        return self


class AIMessageEvent(BaseEvent):
    type: Literal[
        EventType.AI_MESSAGE_STARTED,
        EventType.AI_MESSAGE_CHUNK,
        EventType.AI_MESSAGE_COMPLETED,
        EventType.AI_ERROR,
    ]
    data: AIMessageData


""" File Events """


class FileData(BaseModel):
    id: UUID
    name: str
    file_type: str
    mime_type: str
    file_size: int
    message_id: UUID | None = None
    user_id: UUID
    workspace_id: UUID | None = None
    channel_id: UUID | None = None
    dm_conversation_id: UUID | None = None
    ai_conversation_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_inclusion(self) -> Self:
        if not (
            self.ai_conversation_id
            or self.dm_conversation_id
            or self.channel_id
            or self.workspace_id
            or self.message_id
        ):
            raise ValueError(
                "File must be attached to either a conversation, workspace, or message"
            )
        return self


class FileCreatedEvent(BaseEvent):
    type: Literal[EventType.FILE_CREATED]
    data: FileData


class FileDeletedEvent(BaseEvent):
    type: Literal[EventType.FILE_DELETED]
    data: FileData


""" Workspace Events """


class WorkspaceCreatedEvent(BaseEvent):
    type: Literal[EventType.WORKSPACE_CREATED]
    data: WorkspaceResponse


class WorkspaceUpdatedEvent(BaseEvent):
    type: Literal[EventType.WORKSPACE_UPDATED]
    data: WorkspaceResponse


class WorkspaceDeletedData(BaseModel):
    id: UUID


class WorkspaceDeletedEvent(BaseEvent):
    type: Literal[EventType.WORKSPACE_DELETED]
    data: WorkspaceDeletedData


class WorkspaceMemberAddedData(BaseModel):
    id: UUID
    user_id: UUID
    workspace_id: UUID
    role: WorkspaceRole
    joined_at: datetime


class WorkspaceMemberAddedEvent(BaseEvent):
    type: Literal[EventType.WORKSPACE_MEMBER_ADDED]
    data: WorkspaceMemberAddedData


class WorkspaceMemberRemovedData(BaseModel):
    user_id: UUID
    workspace_id: UUID


class WorkspaceMemberRemovedEvent(BaseEvent):
    type: Literal[EventType.WORKSPACE_MEMBER_REMOVED]
    data: WorkspaceMemberRemovedData


class WorkspaceMemberRoleUpdatedData(BaseModel):
    user_id: UUID
    workspace_id: UUID
    role: WorkspaceRole


class WorkspaceMemberRoleUpdatedEvent(BaseEvent):
    type: Literal[EventType.WORKSPACE_MEMBER_UPDATED]
    data: WorkspaceMemberRoleUpdatedData


class ErrorData(BaseModel):
    error: str
    human_readable_error: str
    user_id: UUID


class ErrorEvent(BaseEvent):
    type: Literal[EventType.ERROR]
    data: ErrorData
