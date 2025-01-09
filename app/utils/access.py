from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.models import ChannelType, Conversation, ConversationMember, WorkspaceMember


def verify_conversation_access(
    session: Session, conversation_id: UUID, user_id: UUID, require_admin: bool = False
) -> Conversation:
    """
    Verify if a user has access to a conversation.
    Returns the conversation if access is granted, raises HTTPException otherwise.
    """
    conversation = session.exec(
        select(Conversation).where(Conversation.id == conversation_id)
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Public channels are accessible to all workspace members
    if conversation.conversation_type == ChannelType.PUBLIC:
        if conversation.workspace_id:
            workspace_member = session.exec(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == conversation.workspace_id,
                    WorkspaceMember.user_id == user_id,
                )
            ).first()
            if not workspace_member:
                raise HTTPException(
                    status_code=403, detail="Not a member of this workspace"
                )
        return conversation

    # For DMs, check if user is a participant
    if conversation.conversation_type == ChannelType.DIRECT:
        if user_id not in [
            conversation.participant_1_id,
            conversation.participant_2_id,
        ]:
            raise HTTPException(
                status_code=403, detail="Not authorized to access this conversation"
            )
        return conversation

    # For private channels, check channel membership
    member = session.exec(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id,
        )
    ).first()

    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this channel")

    if require_admin and not member.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    return conversation


def get_accessible_conversations(
    session: Session, user_id: UUID, workspace_id: UUID | None = None
):
    """Get all conversation IDs that a user has access to in a workspace."""
    query = select(Conversation.id).where(
        or_(
            # Public channels in workspace
            and_(
                Conversation.conversation_type == ChannelType.PUBLIC,
                Conversation.workspace_id == workspace_id,
            )
            if workspace_id
            else False,
            # DMs where user is participant
            and_(
                Conversation.conversation_type == ChannelType.DIRECT,
                or_(
                    Conversation.participant_1_id == user_id,
                    Conversation.participant_2_id == user_id,
                ),
            ),
            # Private channels where user is member
            and_(
                Conversation.conversation_type == ChannelType.PRIVATE,
                Conversation.id.in_(
                    select(ConversationMember.conversation_id).where(
                        ConversationMember.user_id == user_id
                    )
                ),
            ),
        )
    )

    if workspace_id:
        query = query.where(Conversation.workspace_id == workspace_id)

    # Return the UUIDs directly without trying to unpack them
    return session.exec(query).all()


def verify_workspace_access(
    session: Session, workspace_id: UUID, user_id: UUID, require_admin: bool = False
):
    """Verify if a user has access to a workspace."""
    member = session.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    ).first()

    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    if require_admin and member.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    return member
