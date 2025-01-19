from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr


class ReactionResponse(BaseModel):
    id: UUID
    emoji: str
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class FileResponse(BaseModel):
    id: UUID
    name: str
    file_type: str
    mime_type: str
    file_size: int
    s3_key: Optional[str]
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    id: UUID
    content: Optional[str]
    user_id: Optional[UUID]
    is_ai_generated: bool
    file: Optional[FileResponse]
    reactions: List[ReactionResponse]
    replies: List["MessageResponse"]
    created_at: datetime
    updated_at: datetime


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    username: str
    display_name: str
    s3_key: Optional[str]
    is_online: bool
    created_at: datetime
    updated_at: datetime


class WorkspaceMemberResponse(BaseModel):
    id: UUID
    user: UserResponse
    role: str
    joined_at: datetime
    created_at: datetime
    updated_at: datetime


class ChannelResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    slug: str
    s3_key: Optional[str]
    created_by_id: UUID
    messages: List[MessageResponse]
    files: List[FileResponse]
    created_at: datetime
    updated_at: datetime


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    slug: str
    s3_key: Optional[str]
    created_by_id: UUID
    members: List[WorkspaceMemberResponse]
    channels: List[ChannelResponse]
    files: List[FileResponse]
    created_at: datetime
    updated_at: datetime


class DirectMessageConversationResponse(BaseModel):
    id: UUID
    user1: UserResponse
    user2: UserResponse
    messages: List[MessageResponse]
    files: List[FileResponse]
    created_at: datetime
    updated_at: datetime


class AIConversationResponse(BaseModel):
    id: UUID
    messages: List[MessageResponse]
    files: List[FileResponse]
    created_at: datetime
    updated_at: datetime


class DashboardResponse(BaseModel):
    user: UserResponse
    workspaces: List[WorkspaceResponse]
    direct_messages: List[DirectMessageConversationResponse]
    ai_conversation: Optional[AIConversationResponse]
