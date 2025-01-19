from typing import Literal
from uuid import UUID
from sqlmodel import Session

from app.repositories.channel_repository import ChannelRepository
from app.repositories.ai_conversation_repository import AIConversationRepository
from app.repositories.direct_message_repository import DirectMessageRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.repositories.user_repository import UserRepository
from app.repositories.message_repository import MessageRepository


def _get_members_for_conversation(
    conversation_id: UUID,
    db: Session,
    conversation_type: Literal["channel", "dm", "ai"],
) -> list[UUID]:
    member_ids: list[UUID] = []
    if conversation_type == "channel":
        channel_repository = ChannelRepository(db)
        channel = channel_repository.get(conversation_id)
        if channel:
            workspace_repository = WorkspaceRepository(db)
            workspace = workspace_repository.get(channel.workspace_id)
            if workspace and workspace.members:
                for member in workspace.members:
                    member_ids.append(member.id)
    elif conversation_type == "dm":
        direct_message_repository = DirectMessageRepository(db)
        conversation = direct_message_repository.get(conversation_id)
        if conversation:
            if conversation.user1_id:
                member_ids.append(conversation.user1_id)
            if conversation.user2_id:
                member_ids.append(conversation.user2_id)
    elif conversation_type == "ai":
        ai_conversation_repository = AIConversationRepository(db)
        conversation = ai_conversation_repository.get(conversation_id)
        if conversation:
            if conversation.user_id:
                member_ids.append(conversation.user_id)
    return member_ids


def get_members_for_conversations(
    db: Session,
    ai_conversation_id: UUID | None = None,
    channel_id: UUID | None = None,
    dm_conversation_id: UUID | None = None,
) -> list[UUID]:
    member_ids: list[UUID] = []
    if ai_conversation_id:
        member_ids.extend(_get_members_for_conversation(ai_conversation_id, db, "ai"))
    if channel_id:
        member_ids.extend(_get_members_for_conversation(channel_id, db, "channel"))
    if dm_conversation_id:
        member_ids.extend(_get_members_for_conversation(dm_conversation_id, db, "dm"))
    return member_ids


def get_members_for_message(message_id: UUID, db: Session) -> list[UUID]:
    message_repository = MessageRepository(db)
    message = message_repository.get(message_id)
    if message:
        return get_members_for_conversations(
            db,
            ai_conversation_id=message.ai_conversation_id,
            channel_id=message.channel_id,
            dm_conversation_id=message.dm_conversation_id,
        )
    return []


def get_relevant_members_for_user(user_id: UUID, db: Session) -> list[UUID]:
    # We want to get all unique members for all conversations the user is a part of or workspaces the user is a part of
    user_repository = UserRepository(db)
    user = user_repository.get(user_id)
    relevant_id_set = set()
    if user:
        # Get all workspaces the user is a part of
        workspace_repository = WorkspaceRepository(db)
        workspaces = workspace_repository.get_user_workspaces(user_id)
        for workspace in workspaces:
            if workspace.members:
                for member in workspace.members:
                    relevant_id_set.add(member.id)
        # Get all members for all conversations the user is a part of
        direct_message_repository = DirectMessageRepository(db)
        conversations = direct_message_repository.get_all_conversations_for_user(
            user_id
        )
        for conversation in conversations:
            if conversation.user1_id:
                relevant_id_set.add(conversation.user1_id)
            if conversation.user2_id:
                relevant_id_set.add(conversation.user2_id)
    relevant_id_set.add(user_id)
    return list(relevant_id_set)
