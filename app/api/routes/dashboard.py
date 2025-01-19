from typing import Dict, List, Optional, TypeVar, Type
from uuid import UUID
from fastapi import Depends, APIRouter
from pydantic import BaseModel, Field
from datetime import datetime
from sqlmodel import text, Session
from app.models.domain import User
from app.db.session import get_db

from app.api.dependencies import get_current_user


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    display_name: str
    s3_key: Optional[str]
    is_online: bool
    created_at: datetime
    updated_at: datetime


class ReactionResponse(BaseModel):
    id: UUID
    emoji: str
    message_id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class FileResponse(BaseModel):
    id: UUID
    name: str
    file_type: str
    mime_type: str
    file_size: int
    message_id: Optional[UUID]
    user_id: UUID
    workspace_id: Optional[UUID]
    channel_id: Optional[UUID]
    dm_conversation_id: Optional[UUID]
    ai_conversation_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    id: UUID
    content: Optional[str]
    user_id: Optional[UUID]
    is_ai_generated: bool
    channel_id: Optional[UUID]
    dm_conversation_id: Optional[UUID]
    ai_conversation_id: Optional[UUID]
    parent_id: Optional[UUID]
    file_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    reaction_ids: List[UUID] = Field(default_factory=list)
    reply_ids: List[UUID] = Field(default_factory=list)


class ChannelResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    slug: str
    s3_key: Optional[str]
    created_by_id: UUID
    workspace_id: UUID
    created_at: datetime
    updated_at: datetime
    message_ids: List[UUID] = Field(default_factory=list)
    file_ids: List[UUID] = Field(default_factory=list)


class DirectMessageConversationResponse(BaseModel):
    id: UUID
    user1_id: UUID
    user2_id: UUID
    created_at: datetime
    updated_at: datetime
    message_ids: List[UUID] = Field(default_factory=list)
    file_ids: List[UUID] = Field(default_factory=list)


class AIConversationResponse(BaseModel):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    message_ids: List[UUID] = Field(default_factory=list)
    file_ids: List[UUID] = Field(default_factory=list)


class WorkspaceMemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    workspace_id: UUID
    role: str
    joined_at: datetime
    created_at: datetime
    updated_at: datetime


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    slug: str
    s3_key: Optional[str]
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime
    channel_ids: List[UUID] = Field(default_factory=list)
    file_ids: List[UUID] = Field(default_factory=list)
    workspace_member_ids: List[UUID] = Field(default_factory=list)


class DashboardResponse(BaseModel):
    workspaces: Dict[UUID, WorkspaceResponse]
    channels: Dict[UUID, ChannelResponse]
    messages: Dict[UUID, MessageResponse]
    users: Dict[UUID, UserResponse]
    files: Dict[UUID, FileResponse]
    reactions: Dict[UUID, ReactionResponse]
    workspace_members: Dict[UUID, WorkspaceMemberResponse]
    dm_conversations: Dict[UUID, DirectMessageConversationResponse]
    ai_conversations: Dict[UUID, AIConversationResponse]


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
T = TypeVar("T", bound=BaseModel)


def convert_to_dict(items: Optional[List[dict]], model_class: Type[T]) -> Dict[UUID, T]:
    """Convert a list of dictionaries to a dictionary of model instances keyed by ID."""
    if not items or items[0] is None:
        return {}
    return {UUID(item["id"]): model_class(**item) for item in items}


@router.get("", response_model=DashboardResponse)
async def get_dashboard_data(
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DashboardResponse:
    # Create the raw SQL query
    query = """
    WITH RECURSIVE message_tree AS (
        -- Base case: Get all direct messages
        SELECT 
            m.id,
            m.parent_id,
            1 as level
        FROM message m
        -- Join with workspacemember to get all workspaces the user is in
        JOIN workspacemember wm ON wm.user_id = :user_id
        -- Join with channel to get messages in channels
        LEFT JOIN channel c ON m.channel_id = c.id AND c.workspace_id = wm.workspace_id
        -- Get direct messages
        LEFT JOIN directmessageconversation dm ON m.dm_conversation_id = dm.id 
            AND (dm.user1_id = :user_id OR dm.user2_id = :user_id)
        -- Get AI conversation messages
        LEFT JOIN aiconversation ai ON m.ai_conversation_id = ai.id AND ai.user_id = :user_id
        WHERE m.parent_id IS NULL
        
        UNION ALL
        
        -- Recursive case: Get all replies
        SELECT 
            m.id,
            m.parent_id,
            mt.level + 1
        FROM message m
        JOIN message_tree mt ON m.parent_id = mt.id
    )
    
    SELECT
        -- Users
        json_agg(DISTINCT jsonb_build_object(
            'id', u.id,
            'email', u.email,
            'username', u.username,
            'display_name', u.display_name,
            's3_key', u.s3_key,
            'is_online', u.is_online,
            'created_at', u.created_at,
            'updated_at', u.updated_at
        )) AS users,
        
        -- Workspaces
        json_agg(DISTINCT jsonb_build_object(
            'id', w.id,
            'name', w.name,
            'description', w.description,
            'slug', w.slug,
            's3_key', w.s3_key,
            'created_by_id', w.created_by_id,
            'created_at', w.created_at,
            'updated_at', w.updated_at,
            'channel_ids', (
                SELECT json_agg(DISTINCT c.id)
                FROM channel c
                WHERE c.workspace_id = w.id
            ),
            'file_ids', (
                SELECT json_agg(DISTINCT f.id)
                FROM file f
                WHERE f.workspace_id = w.id
            ),
            'workspace_member_ids', (
                SELECT json_agg(DISTINCT wm.id)
                FROM workspacemember wm
                WHERE wm.workspace_id = w.id
            )
        )) AS workspaces,
        
        -- Channels
        json_agg(DISTINCT jsonb_build_object(
            'id', c.id,
            'name', c.name,
            'description', c.description,
            'slug', c.slug,
            's3_key', c.s3_key,
            'created_by_id', c.created_by_id,
            'workspace_id', c.workspace_id,
            'created_at', c.created_at,
            'updated_at', c.updated_at,
            'message_ids', (
                SELECT json_agg(DISTINCT m.id)
                FROM message m
                WHERE m.channel_id = c.id
            ),
            'file_ids', (
                SELECT json_agg(DISTINCT f.id)
                FROM file f
                WHERE f.channel_id = c.id
            )
        )) AS channels,
        
        -- Messages
        json_agg(DISTINCT jsonb_build_object(
            'id', m.id,
            'content', m.content,
            'user_id', m.user_id,
            'is_ai_generated', m.is_ai_generated,
            'channel_id', m.channel_id,
            'dm_conversation_id', m.dm_conversation_id,
            'ai_conversation_id', m.ai_conversation_id,
            'parent_id', m.parent_id,
            'file_id', m.file_id,
            'created_at', m.created_at,
            'updated_at', m.updated_at,
            'reaction_ids', (
                SELECT json_agg(DISTINCT r.id)
                FROM reaction r
                WHERE r.message_id = m.id
            ),
            'reply_ids', (
                SELECT json_agg(DISTINCT reply.id)
                FROM message reply
                WHERE reply.parent_id = m.id
            )
        )) AS messages,
        
        -- Files
        json_agg(DISTINCT jsonb_build_object(
            'id', f.id,
            'name', f.name,
            'file_type', f.file_type,
            'mime_type', f.mime_type,
            'file_size', f.file_size,
            'user_id', f.user_id,
            'workspace_id', f.workspace_id,
            'channel_id', f.channel_id,
            'dm_conversation_id', f.dm_conversation_id,
            'ai_conversation_id', f.ai_conversation_id,
            'created_at', f.created_at,
            'updated_at', f.updated_at
        )) AS files,
        
        -- Reactions
        json_agg(DISTINCT jsonb_build_object(
            'id', r.id,
            'emoji', r.emoji,
            'message_id', r.message_id,
            'user_id', r.user_id,
            'created_at', r.created_at,
            'updated_at', r.updated_at
        )) AS reactions,
        
        -- Workspace Members
        json_agg(DISTINCT jsonb_build_object(
            'id', wm.id,
            'user_id', wm.user_id,
            'workspace_id', wm.workspace_id,
            'role', wm.role,
            'joined_at', wm.joined_at,
            'created_at', wm.created_at,
            'updated_at', wm.updated_at
        )) AS workspace_members,
        
        -- DM Conversations
        json_agg(DISTINCT jsonb_build_object(
            'id', dm.id,
            'user1_id', dm.user1_id,
            'user2_id', dm.user2_id,
            'created_at', dm.created_at,
            'updated_at', dm.updated_at,
            'message_ids', (
                SELECT json_agg(DISTINCT m.id)
                FROM message m
                WHERE m.dm_conversation_id = dm.id
            ),
            'file_ids', (
                SELECT json_agg(DISTINCT f.id)
                FROM file f
                WHERE f.dm_conversation_id = dm.id
            )
        )) AS dm_conversations,
        
        -- AI Conversations
        json_agg(DISTINCT jsonb_build_object(
            'id', ai.id,
            'user_id', ai.user_id,
            'created_at', ai.created_at,
            'updated_at', ai.updated_at,
            'message_ids', (
                SELECT json_agg(DISTINCT m.id)
                FROM message m
                WHERE m.ai_conversation_id = ai.id
            ),
            'file_ids', (
                SELECT json_agg(DISTINCT f.id)
                FROM file f
                WHERE f.ai_conversation_id = ai.id
            )
        )) AS ai_conversations
        
    FROM workspacemember wm
    JOIN workspace w ON wm.workspace_id = w.id
    JOIN app_user u ON wm.user_id = u.id
    LEFT JOIN channel c ON c.workspace_id = w.id
    LEFT JOIN message m ON 
        (m.channel_id = c.id) OR
        (m.id IN (SELECT id FROM message_tree))
    LEFT JOIN file f ON 
        f.workspace_id = w.id OR
        f.channel_id = c.id OR
        m.file_id = f.id
    LEFT JOIN reaction r ON r.message_id = m.id
    LEFT JOIN directmessageconversation dm ON 
        (dm.user1_id = :user_id OR dm.user2_id = :user_id)
    LEFT JOIN aiconversation ai ON ai.user_id = :user_id
    WHERE wm.user_id = :user_id;
    """

    # Execute the query
    result = session.execute(text(query), {"user_id": user.id})
    row = result.fetchone()

    # Return empty data if no results found
    if not row:
        return DashboardResponse(
            users={},
            workspaces={},
            channels={},
            messages={},
            files={},
            reactions={},
            workspace_members={},
            dm_conversations={},
            ai_conversations={},
        )

    # Build the response
    return DashboardResponse(
        users=convert_to_dict(row.users, UserResponse),
        workspaces=convert_to_dict(row.workspaces, WorkspaceResponse),
        channels=convert_to_dict(row.channels, ChannelResponse),
        messages=convert_to_dict(row.messages, MessageResponse),
        files=convert_to_dict(row.files, FileResponse),
        reactions=convert_to_dict(row.reactions, ReactionResponse),
        workspace_members=convert_to_dict(
            row.workspace_members, WorkspaceMemberResponse
        ),
        dm_conversations=convert_to_dict(
            row.dm_conversations, DirectMessageConversationResponse
        ),
        ai_conversations=convert_to_dict(row.ai_conversations, AIConversationResponse),
    )
