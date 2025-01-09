from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, and_, or_, select
from sqlalchemy import Engine
from typing import List
from uuid import UUID
from pydantic import BaseModel

from app.utils.db import get_db
from app.models import Conversation, User, ChannelType
from app.utils.auth import get_current_user
from app.schemas import ConversationInfo
from app.utils.access import verify_workspace_access, get_accessible_conversations

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    name: str | None = None  # Required for channels, optional for DMs
    description: str | None = None  # For channels only
    conversation_type: ChannelType
    participant_id: UUID | None = None  # Required for DMs
    workspace_id: UUID | None = None  # Required for channels


@router.post("", response_model=ConversationInfo)
async def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Create a new conversation (channel or DM)."""
    with Session(engine) as session:
        if data.conversation_type == ChannelType.DIRECT:
            if not data.participant_id:
                raise HTTPException(
                    status_code=400,
                    detail="participant_id required for DM conversations",
                )

            # Check if DM conversation already exists
            existing_conversation = session.exec(
                select(Conversation).where(
                    Conversation.conversation_type == ChannelType.DIRECT,
                    or_(
                        and_(
                            Conversation.participant_1_id == current_user.id,
                            Conversation.participant_2_id == data.participant_id,
                        ),
                        and_(
                            Conversation.participant_1_id == data.participant_id,
                            Conversation.participant_2_id == current_user.id,
                        ),
                    ),
                )
            ).first()

            if existing_conversation:
                # Convert UUIDs to strings in the model dump
                data = existing_conversation.model_dump()
                data["id"] = str(data["id"])
                if data.get("workspace_id"):
                    data["workspace_id"] = str(data["workspace_id"])
                return ConversationInfo.model_validate(data)

            # Create new DM conversation
            conversation = Conversation(
                conversation_type=ChannelType.DIRECT,
                participant_1_id=current_user.id,
                participant_2_id=data.participant_id,
            )
        else:
            # Creating a channel
            if not data.name:
                raise HTTPException(
                    status_code=400, detail="name required for channel conversations"
                )
            if not data.workspace_id:
                raise HTTPException(
                    status_code=400,
                    detail="workspace_id required for channel conversations",
                )

            # Verify workspace access
            verify_workspace_access(session, data.workspace_id, current_user.id)

            conversation = Conversation(
                name=data.name,
                description=data.description,
                conversation_type=data.conversation_type,
                workspace_id=data.workspace_id,
            )

        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        # Convert UUIDs to strings in the model dump
        data = conversation.model_dump()
        data["id"] = str(data["id"])
        if data.get("workspace_id"):
            data["workspace_id"] = str(data["workspace_id"])
        return ConversationInfo.model_validate(data)


@router.get("/recent", response_model=List[ConversationInfo])
async def get_recent_conversations(
    workspace_id: UUID | None = None,
    conversation_type: ChannelType | None = None,
    limit: int = Query(default=20, le=50),
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get recent conversations (channels or DMs) for the current user."""
    with Session(engine) as session:
        # If workspace specified, verify access
        if workspace_id:
            verify_workspace_access(session, workspace_id, current_user.id)

        # Get accessible conversation IDs
        conversation_ids = get_accessible_conversations(
            session, current_user.id, workspace_id
        )

        # Build query
        query = select(Conversation).where(Conversation.id.in_(conversation_ids))

        # Add type filter if specified
        if conversation_type:
            query = query.where(Conversation.conversation_type == conversation_type)

        # Order by most recent activity and apply limit
        query = query.order_by(Conversation.updated_at.desc()).limit(limit)

        # Execute query
        conversations = session.exec(query).all()

        # Convert to response model
        return [
            ConversationInfo.model_validate(conv.model_dump()) for conv in conversations
        ]
