from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models import ChannelType, FileType


class UserBase(BaseModel):
    """Base user fields"""

    email: EmailStr
    username: str
    display_name: Optional[str] = None


class UserCreate(UserBase):
    """Fields required to create a user"""

    password: str


class UserLogin(BaseModel):
    """Fields required to login"""

    email: str
    password: str


class UserInfo(UserBase):
    """User information returned in responses"""

    id: str
    avatar_url: Optional[str] = None
    is_online: bool = False


class UserProfile(UserInfo):
    """Extended user profile information"""

    created_at: datetime
    last_active: datetime
    status: Optional[str] = None


class MessageInfo(BaseModel):
    id: str
    content: str
    conversation_id: str
    parent_id: str | None
    created_at: datetime
    updated_at: datetime
    reply_count: int = 0
    user: UserInfo
    attachments: List["FileInfo"] = []
    reactions: List["ReactionInfo"] = []


class FileInfo(BaseModel):
    id: str
    original_filename: str
    file_type: FileType
    mime_type: str
    file_size: int
    uploaded_at: datetime
    download_url: Optional[str] = None


class ReactionInfo(BaseModel):
    id: str
    emoji: str
    user: UserInfo


class ConversationInfo(BaseModel):
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    conversation_type: ChannelType
    workspace_id: Optional[str] = None
    participant_1: Optional[UserInfo] = None
    participant_2: Optional[UserInfo] = None
    last_message: Optional[MessageInfo] = None
    created_at: datetime
    updated_at: datetime


class WorkspaceInfo(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    slug: str
    created_at: datetime
    created_by_id: UUID
    member_count: Optional[int] = None


class ChannelMemberInfo(BaseModel):
    user: UserInfo
    is_admin: bool
    joined_at: datetime


class TokenResponse(BaseModel):
    """Response containing authentication tokens"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    """Response for authentication endpoints"""

    user: UserInfo
    tokens: Optional[TokenResponse] = None


class WorkspaceMemberInfo(BaseModel):
    """Workspace member information"""

    user_id: str
    role: str
    joined_at: datetime


MessageInfo.model_rebuild()  # Rebuild to handle circular references
