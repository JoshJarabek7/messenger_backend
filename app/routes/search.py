from fastapi import APIRouter, Depends, Query, HTTPException
from sqlmodel import Session, select, or_, and_
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from enum import Enum

from app.utils.db import get_session
from app.models import (
    User, Workspace, WorkspaceMember, Conversation, 
    Message, FileAttachment, ChannelType, ConversationMember
)
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/search", tags=["search"])

class SearchType(str, Enum):
    MESSAGES = "messages"
    FILES = "files"
    USERS = "users"
    WORKSPACES = "workspaces"
    ALL = "all"

@router.get("/global")
async def search_global(
    query: str = Query(..., min_length=1),
    search_type: SearchType = SearchType.ALL,
    workspace_id: Optional[UUID] = None,
    conversation_id: Optional[UUID] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Search across all content types or specific types.
    Can be scoped to a workspace or conversation.
    """
    results = {}

    if search_type in [SearchType.USERS, SearchType.ALL]:
        # Search for users
        user_query = select(User).where(
            or_(
                User.username.ilike(f"%{query}%"),
                User.display_name.ilike(f"%{query}%"),
                User.email.ilike(f"%{query}%")
            )
        )

        if workspace_id:
            user_query = user_query.join(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)

        users = session.exec(user_query).all()
        results["users"] = [
            {
                "id": str(user.id),
                "username": user.username,
                "display_name": user.display_name,
                "avatar_url": user.avatar_url,
                "email": user.email,
                "is_online": user.is_online
            }
            for user in users
        ]

    if search_type in [SearchType.WORKSPACES, SearchType.ALL]:
        # Search for workspaces
        workspace_query = (
            select(Workspace, WorkspaceMember)
            .outerjoin(WorkspaceMember, and_(
                WorkspaceMember.workspace_id == Workspace.id,
                WorkspaceMember.user_id == current_user.id
            ))
            .where(
                or_(
                    Workspace.name.ilike(f"%{query}%"),
                    Workspace.slug.ilike(f"%{query}%")
                )
            )
        )

        workspaces_with_membership = session.exec(workspace_query).all()
        results["workspaces"] = [
            {
                "id": str(workspace.id),
                "name": workspace.name,
                "icon_url": workspace.icon_url,
                "slug": workspace.slug,
                "is_member": bool(member)
            }
            for workspace, member in workspaces_with_membership
        ]

    if search_type in [SearchType.MESSAGES, SearchType.ALL]:
        # Build base message query
        message_query = (
            select(Message, User)
            .join(User, Message.user_id == User.id)
            .where(Message.content.ilike(f"%{query}%"))
        )

        # Add scope filters
        if conversation_id:
            message_query = message_query.where(Message.conversation_id == conversation_id)
        elif workspace_id:
            # Get all conversations in workspace user has access to
            accessible_conversations = (
                select(Conversation.id)
                .where(
                    Conversation.workspace_id == workspace_id,
                    or_(
                        Conversation.conversation_type == ChannelType.PUBLIC,
                        and_(
                            Conversation.conversation_type == ChannelType.DIRECT,
                            or_(
                                Conversation.participant_1_id == current_user.id,
                                Conversation.participant_2_id == current_user.id
                            )
                        ),
                        and_(
                            Conversation.conversation_type == ChannelType.PRIVATE,
                            Conversation.id.in_(
                                select(ConversationMember.conversation_id)
                                .where(ConversationMember.user_id == current_user.id)
                            )
                        )
                    )
                )
            )
            message_query = message_query.where(Message.conversation_id.in_(accessible_conversations))

        messages = session.exec(message_query).all()
        results["messages"] = [
            {
                "id": str(message.id),
                "content": message.content,
                "conversation_id": str(message.conversation_id),
                "created_at": message.created_at.isoformat(),
                "user": {
                    "id": str(user.id),
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar_url": user.avatar_url
                }
            }
            for message, user in messages
        ]

    if search_type in [SearchType.FILES, SearchType.ALL]:
        # Build base file query
        file_query = (
            select(FileAttachment, User, Message)
            .join(User, FileAttachment.user_id == User.id)
            .join(Message, FileAttachment.message_id == Message.id)
            .where(
                or_(
                    FileAttachment.original_filename.ilike(f"%{query}%"),
                    Message.content.ilike(f"%{query}%")
                )
            )
        )

        # Add scope filters
        if conversation_id:
            file_query = file_query.where(Message.conversation_id == conversation_id)
        elif workspace_id:
            # Use the same accessible conversations logic as messages
            accessible_conversations = (
                select(Conversation.id)
                .where(
                    Conversation.workspace_id == workspace_id,
                    or_(
                        Conversation.conversation_type == ChannelType.PUBLIC,
                        and_(
                            Conversation.conversation_type == ChannelType.DIRECT,
                            or_(
                                Conversation.participant_1_id == current_user.id,
                                Conversation.participant_2_id == current_user.id
                            )
                        ),
                        and_(
                            Conversation.conversation_type == ChannelType.PRIVATE,
                            Conversation.id.in_(
                                select(ConversationMember.conversation_id)
                                .where(ConversationMember.user_id == current_user.id)
                            )
                        )
                    )
                )
            )
            file_query = file_query.where(Message.conversation_id.in_(accessible_conversations))

        files = session.exec(file_query).all()
        results["files"] = [
            {
                "id": str(file.id),
                "original_filename": file.original_filename,
                "file_type": file.file_type,
                "mime_type": file.mime_type,
                "file_size": file.file_size,
                "uploaded_at": file.uploaded_at.isoformat(),
                "user": {
                    "id": str(user.id),
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar_url": user.avatar_url
                },
                "message": {
                    "id": str(message.id),
                    "content": message.content,
                    "conversation_id": str(message.conversation_id)
                }
            }
            for file, user, message in files
        ]

    return results 